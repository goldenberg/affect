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
import vary_c
import make_kernels
import numpy
import os
import subprocess
import shutil

import drmaa

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('add_kernels')

def main():
    usage = """%prog KERNEL1 KERNEL2 OUTPUT_BASENAME [options]
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-l", "--log_level", action="store", 
                       default='warning', dest="log_level")
    
    options, arguments = opt_parser.parse_args()
    
    log.setLevel(LOG_LEVELS[options.log_level])
    
    run_svms(arguments[0], arguments[1], arguments[2])

def run_svms(kernel1, kernel2, basename):    
    if os.path.exists(basename):
        shutil.rmtree(basename)
    
    os.makedirs(basename)
    
    c_values = numpy.arange(0.1, 5, 1)
    
    svmin_path = os.path.realpath('sentences.all')
    
    data_points = []
    for weight in numpy.arange(0, 1, 0.1):
        kernel_filename = os.path.join(basename, str(weight) + '.kar')
        add_kernels(kernel1, kernel2, kernel_filename, weight1=1-weight, weight2=weight)
        matrix_filename = os.path.realpath(make_kernels.compile_kernel(kernel_filename))
        
        weight_folder = os.path.join(basename, 'weight=%s' % str(weight))
        os.mkdir(weight_folder)
        
        job_templates = vary_c.init_drmaa_job_templates(session, 'svm-train', 
                                    c_values, matrix_filename, svmin_path, weight_folder)
        
        
        #data_points.append( {'weight1' : 1-weight, 
        #                     'weight2' : weight, 
        #                     'accuracy' : accuracy,
        #                     'c' : c,
        #                    } )
    
    #save_accuracies(data_points, basename)
    #plot_accuracies(data_points, basename)

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
    output = open(basename + '.tsv', 'w')
    
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
        log.error('klsum: ' + stderr)
    
    output_file.close()


if __name__ == "__main__":
    main()
