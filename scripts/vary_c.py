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

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

log = logging.getLogger(__name__)

def main():
    usage = """%prog C_BEGIN C_END C_STEP SVM_ARGS [options]
            """
    
    c_begin = float(sys.argv[1])
    c_end = float(sys.argv[2])
    c_step = float(sys.argv[3])
    
    svm_args = sys.argv[4:]
        
    for c in np.arange(c_begin, c_end, c_step):
        output = run_svmtrain(svm_args, c)
        accuracy = find_cv_accuracy(output)
        print 'c = %.3f, accuracy = %.2f' % (c, accuracy)
    
def run_svmtrain(svm_args, c):
    '''
    Runs svm-train with all the specified arguments and c. Returns the output
    as a string.
    '''
    arguments = ["svm-train", "-c", "%f" % c]
    arguments.extend(svm_args)
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE)
    (stdout, stderr) = process.communicate()
    return stdout

def find_cv_accuracy(output):
    '''
    Takes the output from svm-train and finds the CV accuracy and returns it
    as a float.
    '''
    for line in output.split('\n'):
        if line.startswith('Cross Validation Accuracy'):
            return float(line.split(' ')[-1][:-1])

if __name__ == "__main__":
    main()
