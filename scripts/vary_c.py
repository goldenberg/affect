#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-06-23.
Copyright (c) 2009. All rights reserved.
"""

import sys
import optparse
import logging
import numpy as np
import subprocess
import pdb
import os

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

log = logging.getLogger('vary_c')

def main():
    usage = """%prog C_BEGIN C_END C_STEP OUTPUT_FILE SVM_ARGS [options]
            """
    
    c_begin = float(sys.argv[1])
    c_end = float(sys.argv[2])
    c_step = float(sys.argv[3])
    output_basename = sys.argv[4]
    
    svm_args = sys.argv[5:]
    
    run_svms(c_begin, c_end, c_step, svm_args, output_basename)

def run_svms(c_begin, c_end, c_step, svm_args, output_basename):
    accuracies = []
    c_values = np.arange(c_begin, c_end, c_step)
    for c in c_values:
        output = run_svmtrain(svm_args, c)
        accuracy = find_cv_accuracy(output)
        accuracies.append(accuracy)
        print 'accuracy = %.2f when c = %.3f' % (accuracy, c)
    
    max_accuracy, max_c = max(zip(accuracies, c_values))
    print 'best accuracy = %.2f when c = %.3f' % (max_accuracy, max_c)
    
    plot_accuracies(c_values, accuracies, output_basename)
    save_accuracies(c_values, accuracies, output_basename)
    
    return max_c, max_accuracy

def run_svmtrain(svm_args, c):
    '''
    Runs svm-train with all the specified arguments and c. Returns the output
    as a string.
    '''
    arguments = ["svm-train", "-c", "%f" % c]
    arguments.extend(svm_args)
    
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE)
    (stdout, stderr) = process.communicate()
    
    return stdout

def init_drmaa_job_templates(session, svmtrain_path, c_values, kernel_path, svmin_path, output_folder):    
    '''
    Returns a list of DRMAA job templates with varying c-parameter. Outputs
    will be stored a c=%s.svmout file
    '''
    
    templates = []
    
    for c in c_values:
        job_template = session.createJobTemplate()
        job_template.remoteCommand = svmtrain_path
        job_template.args = ['-c', '%f' % c, '-k', 'openkernel', '-K', '-v', '10', kernel_path, svmin_path]
        job_template.outputPath = ':' + os.path.join(drmaa.JobTemplate.WORKING_DIRECTORY, 'c=%s.svmout' % str(c))
        job_template.environment = {'LD_LIBRARY_PATH': '/data/x86_64/OpenKernel/kernel/plugin/:/data/x86_64/OpenFst/lib/'}
        templates.append(job_template)
    
    return templates

def find_cv_accuracy(output):
    '''
    Takes the output from svm-train and finds the CV accuracy and returns it
    as a float.
    '''
    for line in output.split('\n'):
        if line.startswith('Cross Validation Accuracy'):
            return float(line.split(' ')[-1][:-1])

def plot_accuracies(c_values, accuracies, basename):
    '''
    Plots the c-values v. accuracies and saves the figure to basename + .pdf
    '''
    try:
        import pylab
    except ImportError, e:
        log.error('pylab is unavailable on this machine. The accuracies will not be plotted.')
        return
    
    fig = pylab.figure()
    pylab.xlabel('$c$ (SVM cost parameter)')
    pylab.ylabel('% accuracy')
    pylab.plot(c_values, accuracies)
    pylab.savefig(basename + '.pdf')

def save_accuracies(c_values, accuracies, basename):
    '''
    Saves a TSV of all accuracies.
    '''
    output = open(basename + '.tsv', 'w')
    for c, accuracy in zip(c_values, accuracies):
        output.write('%.3f\t%.3f\n' % (c, accuracy))
    
    output.close()

if __name__ == "__main__":
    main()
