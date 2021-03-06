#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-07-26.
Copyright (c) 2009. All rights reserved.
"""

import sys
import optparse
import logging
import make_kernels
from decimal import Decimal
import os
import subprocess
import shutil
import re
import drmaa

import pdb
from svm_job import SVMJob

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

CLUSTER_ENVIRONMENT = {'LD_LIBRARY_PATH': '/g/reu09/goldenbe/OpenKernel/kernel/lib'
                                          ':/data/x86_64/OpenFst/lib/'
                                          ':/g/reu09/goldenbe/OpenKernel/kernel/plugin'}

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('add_kernels')

def main():
    usage = """%prog KERNEL1 KERNEL2 SVM_FILE OUTPUT_BASENAME [options]
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-l", "--log_level", action="store", 
                       default='debug', dest="log_level")
    
    opt_parser.add_option("-v", "--cross_validate", action="store", type=int,
                       help="Specify n for n-fold cross-validation")
    
    opt_parser.add_option("-t", "--svm_test_file", action="store",
                       help="If not cross-validating, specify a test dataset.")
    
    opt_parser.add_option("-o", "--leave_one_out", action="store_true",
                       help="Perform leave one out cross validation using "
                       "leave_one_out_svm.py")

    options, arguments = opt_parser.parse_args()
    
    
    
    if len(arguments) != 4:
        opt_parser.error("You must specify all four arguments (-v, -o or -t)")
    if options.svm_test_file == options.cross_validate == options.leave_one_out == None:
        opt_parser.error("You must either specify cross-validation using -v or"
                         " -l or a test data set using -t")
    
    kernel1 = arguments[0]
    kernel2 = arguments[1]
    svm_train_file = arguments[2]
    output_basename = arguments[3]
    
    # create output folder
    if os.path.exists(output_basename):
        shutil.rmtree(output_basename)
    
    os.makedirs(output_basename)
    
    log.setLevel(LOG_LEVELS[options.log_level])
    
    weight_range = drange(Decimal('0.0'), Decimal('1.0'), Decimal('0.1'))
    session = drmaa.Session()
    
    sum_all_kernels(None, kernel1, kernel2, weight_range, output_basename)
    
    if options.cross_validate:
        cross_val_option = options.cross_validate
    elif options.leave_one_out:
        
        cross_val_option = SVMJob.LEAVE_ONE_OUT_CV
    else:
        cross_val_option = None
    
    svm_jobs = create_svm_jobs(session, output_basename, svm_train_file, cross_val_option)
    job_templates = [sj.setup_drmaa_job(session) for sj in svm_jobs]
    job_ids = [session.runJob(jt) for jt in job_templates]
    
    log.info('SVM jobs submitted')
    session.synchronize(job_ids)
    log.info('All SVM jobs synchronized')
    
    data_points = convert_jobs_to_datapoints(svm_jobs)
    save_accuracies(data_points, output_basename)
    
    best_point = max(data_points, key=lambda x: x['accuracy'])
    print 'Best accuracy: %(accuracy)s when c=%(c)s and weight=%(weight2)s' % best_point
    
def create_svm_jobs(session, kernel_directory, svmin_path, cross_val=None):    
    '''
    Runs distributed SVMs across a DRMAA cluster. JobTemplates are created by
    vary_c.init_drmaa_job_templates. The following directory structure is used:
    
    ./weight=0.xx/c=x.xx.svmout
                 /c=x.xx.svmerr
    '''
    
    c_values = list(drange(Decimal('0.1'), Decimal('8'), Decimal('.1')))
    
    svm_train = '/g/reu09/goldenbe/OpenKernel/libsvm-2.82/svm-train'
    
    all_svm_jobs = []
    
    for kernel_filename in os.listdir(kernel_directory):
        if not kernel_filename.endswith('.kar'):
            log.debug('found kernel: %s' % kernel_filename)
            continue
        
        kernel_path = os.path.realpath(os.path.join(kernel_directory, kernel_filename))
        
        # directory at same level as kernel to store svm outputs
        output_directory = os.path.splitext(kernel_path)[0]
        if os.path.exists(output_directory):
            shutil.rmtree(output_directory)
        
        os.mkdir(output_directory)
        
        for c in c_values:
            svm_job = SVMJob()
            
            svm_job.c_value = c
            svm_job.kernel_path = kernel_path
            svm_job.cross_validation = cross_val
            svm_job.training_file = svmin_path
            svm_job.svmtrain_path = svm_train
            svm_job.output_basename = os.path.join(output_directory, 'c' + str(c))
            
            svm_job.metadata['weight'] = parse_weight_from_kernel_filename(kernel_filename)
            
            all_svm_jobs.append(svm_job)
    
    return all_svm_jobs

def parse_weight_from_kernel_filename(filename):
    '''
    Returns the weight parsed from the kernel filename.
    
    >> parse_weight_from_kernel_filename('weight0.4.kar')
    0.4
    '''
    regex = re.compile(r'weight(\d*.\d*).kar')
    
    return float(regex.findall(filename)[0])
    

def convert_jobs_to_datapoints(svm_jobs):
    '''
    Converts SVMJob objects to data point dicts with keys: weight1, weight2,
    accuracy, c.
    '''
    data_points = []
    
    for job in svm_jobs:
        data_points.append({'weight1' : 1 - job.metadata['weight'],
                            'weight2' : job.metadata['weight'],
                            'accuracy' : job.get_accuracy(),
                            'c' : job.c_value})
    
    return data_points

def read_all_accuracies(root_directory):
    '''
    Reads a directory of the form weightX.XX/cX.X.svmout into a list of dicts
    with keys: weight1, weight2, accuracy, c.
    '''
    data_points = []
    for (dirpath, dirnames, filenames) in os.walk(root_directory):
        dir_name = os.path.split(dirpath)[1]
        
        if dir_name.startswith('weight'):
            for svmout_filename in filenames:
                if svmout_filename.startswith('c') and svmout_filename.endswith('.svmout'):
                    svmout_path = os.path.join(dirpath, svmout_filename)
                    svmoutput = ''.join(open(svmout_path).readlines())
                    #accuracy = vary_c.find_cv_accuracy(svmoutput)
                    weight = float(dir_name[6:])
                    c = float(svmout_filename[1:-7])
                    
                    data_points.append( {'weight1' : 1 - weight,
                                         'weight2' : weight,
                                         'accuracy' : Decimal('%3f' % accuracy),
                                         'c' : c})
    
    return data_points

def plot_accuracies(data_points, basename):
    '''
    Plot the ratio of weight1 to weight2 versus the SVM accuracy for the 
    summed kernel.
    '''
    try:
        import pylab
    except ImportError, e:
        log.error('pylab cannot be loaded. The data will not be plotted.')
        return
    
    ratios = [point['weight1'] / point['weight2'] for point in data_points]
    accuracies = [point['accuracy'] for point in data_points]
    
    fig = pylab.figure()
    pylab.xlabel('$\alpha1$ / $\alpha2$ (weight ratio)')
    pylab.ylabel('% accuracy')
    pylab.plot(ratios, accuracies)
    pylab.savefig(basename + '.pdf')

def save_accuracies(data_points, basename):
    '''
    Saves a TSV file of all the accuracies for each ratio and their
    corresponding best c value.
    '''
    output = open(os.path.join(basename, 'accuracy.tsv'), 'w')
    
    for point in data_points:
        fields = [point['weight1'], point['weight2'], point['c'], point['accuracy']]
        output.write('\t'.join([str(field) for field in fields]) + '\n')
    
    output.close()

def add_kernels(kernel1, kernel2, output_filename, weight1=1, weight2=1):
    '''
    Calls klsum with the passed kernel paths and weights.
    '''
    output_file = open(output_filename, 'wb')
    
    log.info('%.2f * %s + %.2f * %s' % (weight1, os.path.basename(kernel1), 
                                        weight2, os.path.basename(kernel2)))
    
    arguments = ['klsum', '--alpha1=%.3f' % weight1,
                          '--alpha2=%.3f' % weight2, 
                          kernel1, kernel2]
    
    assert os.path.exists(kernel1)
    assert os.path.exists(kernel2)
    
    popen = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    stdout, stderr = popen.communicate()
    
    output_file.write(stdout)
    
    for line in stderr.split('\n'):
        if line.strip() != '':
            log.error('klsum: ' + line)
    
    output_file.close()


def sum_all_kernels(session, kernel1, kernel2, weight_range, output_folder):
    '''
    Submits jobs to the DRMAA session to add and compile the two kernels.
    Waits to synchronize all jobs. If session==None, sum locally. 
    '''
    if not session:
        for weight in weight_range:
            kernel_filename = os.path.join(output_folder, 'weight%s.kar' % weight)
            add_kernels(kernel1, kernel2, kernel_filename, Decimal('1') - weight, weight)
        
        return
    
    KLSUM_PATH = '/g/reu09/goldenbe/OpenKernel/kernel/bin/klsum'
    
    summed_kernel_path = ':' + drmaa.JobTemplate.WORKING_DIRECTORY + os.path.join(output_folder, 'weight%s.kar') 
    kernel1_path = os.path.realpath( kernel1 )
    kernel2_path = os.path.realpath(kernel2)
    
    job_templates = []
    
    for weight in weight_range:
        job_template = session.createJobTemplate()
        
        weight1 = Decimal('1') - weight
        weight2 = weight
        
        job_template.remoteCommand = KLSUM_PATH
        job_template.arguments = [ 
                                   kernel1_path, kernel2_path ]
        
        job_template.environment = CLUSTER_ENVIRONMENT
                
        job_template.workingDirectory = os.getcwd()
        job_template.outputPath = summed_kernel_path % weight
        job_template.errorPath  = (summed_kernel_path + '.err') % weight
        
        job_template.nativeSpecification = '-q penguin.q'
        
        job_templates.append(job_template)
        
    job_ids = [session.runJob(jt) for jt in job_templates]
    
    log.info('summing jobs started. ids: %s' % job_ids)
    session.synchronize(job_ids, drmaa.Session.TIMEOUT_WAIT_FOREVER, False)


def read_accuracies(data_points, filename):
    '''
    Read data points back from accuracy.tsv file.
    '''
    
    data_points = []
    
    for line in open(filename):
        fields = line.split(' ')
        
        data_points.append( {'weight1' : float(fields[0]),
                             'weight2' : float(fields[1]),
                             'c' : float(fields[2]),
                             'accuracy' : Decimal(fields[3])})
    
    return data_points

def drange(start, stop, step):
    '''
    Yields value from start up to and incuding stop (unlike builtin range())
    Should work for any object with + and < defined
    '''
    r = start
    while r <= stop:
        yield r
        r += step

if __name__ == "__main__":
    main()
