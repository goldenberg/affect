#!/usr/bin/env python
# encoding: utf-8
"""
leave_one_out_svm.py

Created by Benjamin Goldenberg on 2009-08-07.
Copyright (c) 2009. All rights reserved.
"""

import os
import sys
import optparse
import logging
import linecache
import subprocess

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

log = logging.getLogger(__name__)

def main():
    usage = """%prog INPUT_FILE SVM_ARGS
            """
    
    
    dataset_file = sys.argv[1]
    svm_args = sys.argv[2:]
    
    # read lines and filter out any whitespace lines
    lines = open(dataset_file).readlines()    
    lines = filter(lambda line: line.strip() != '', lines)
    
    # write out all the split files
    [split_data(lines, i, dataset_file) for i in range(1, len(lines)+1)]
    
    # run all svms
    successes = sum([run_svm(dataset_file, i, svm_args) for i in range(1, len(lines)+1)])
    
    print '%i successes (%.2f%% accuracy)' % (successes, successes * 100.0 / len(lines))

def run_svm(output_basename, index, svm_args):
    """
    Runs svm-train and svm-predict on basename.index.{train, test}. Returns
    the percentage accuracy as a float [0,1] (should be 0 or 1 for leave one out)
    """
    train_file = '%s.%i.train' % (output_basename, index)
    test_file  = '%s.%i.test'  % (output_basename, index)
    model_file = '%s.%i.model' % (output_basename, index)
    output_file= '%s.%i.output'% (output_basename, index)
    
    train_args = ['svm-train'] + svm_args + [train_file, model_file]
    train_proc = subprocess.Popen(train_args, stderr=subprocess.PIPE, 
                                    stdout=subprocess.PIPE)
    train_proc.communicate()
    
    test_args = ['svm-predict', test_file, model_file, output_file]
    test_proc = subprocess.Popen(test_args, stderr=subprocess.PIPE, 
                                    stdout=subprocess.PIPE)
    
    stdout, stderr = test_proc.communicate()
    
    return parse_accuracy(stdout)

def parse_accuracy(stdout):
    """
    Looks for the string a back slash, which should be found as in (0/1) 
    and returns the percentage accuracy as a float.
    """
    slash_index = stdout.find('/')
    
    return float(stdout[slash_index-1]) / float(stdout[slash_index+1])

def split_data(lines, index, output_basename):
    """
    Splits an SVM input file into two files, one training file with n-1
    vectors and one test file with 1 vector. The files will be named
    output_basename.index.{train, test}
    """
    
    train = open('%s.%i.train' % (output_basename, index), 'w')
    test = open('%s.%i.test' % (output_basename, index), 'w')
    
    train.writelines(lines[:index-1] + lines[index:])
    test.write(lines[index-1])
    
    train.close()
    test.close()


if __name__ == "__main__":
    main()

