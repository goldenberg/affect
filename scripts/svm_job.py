#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-08-10.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

import sys
import os
import unittest
import logging

log = logging.getLogger('svm_job')

class SVMJob:
    LEAVE_ONE_OUT_CV = -1
    
    c = property(doc="SVM cost parameter.")
    kernel = property(doc="OpenKernel kernel file")
    cross_validation = property(doc="Either an integer for n-fold cross "
                            "validation or LEAVE_ONE_OUT for leave-one-out cv.")
    training_file = property(doc="Training file")
    svmtrain_path = property(doc="Path to svm-train executable. Uses executable on path if not set.")
    svmpredict_path = property(doc="Path to svm-predict executable. Uses executable on path if not set.")
    leave_one_out_path = property(doc="Path to leave_one_out_svm.py")
    native_specifications = property(doc="Arguments to pass through to SGE")
    
    def __init__(self, c=1, kernel=None, cross_validation=None, training_file=None, output_basename):
        self.c = c
        self.kernel_path = kernel
        self.cross_validation = cross_validation
        self.training_file = training_file
        self.output_basename = output_basename
        
        self.svmtrain_path = 'svm-train'
        self.svmpredict_path = 'svm-predict'
        self.leave_one_out_path = '~/affect/scripts/leave_one_out_svm.py'
        
        self.native_specifications = '-q penguin.q'
        self.job_environment = {'LD_LIBRARY_PATH': '/g/reu09/goldenbe/OpenKernel/kernel/lib'
                                                   ':/data/x86_64/OpenFst/lib/'
                                                   ':/g/reu09/goldenbe/OpenKernel/kernel/plugin'}
    
    def run_local_train():
        '''
        Assumes svm-train is on the path. If not pass an absolute path.
        '''
        args = self.generate_train_args()
        
        args.insert(0, self.svmtrain_path)
        
        output_path = self.output_basename + '.svmout'
        error_path = self.output_basename + '.svmerr'
        
        process = subprocess.Popen(arguments, stdout=open(output_path), stderr=open(error_path))
        (stdout, stderr) = process.communicate()
    
    def setup_drmaa_job(session):
        '''
        Returns a DRMAA job template with all the necessary info to run.
        '''
        try:
            import drmaa
        except ImportError, e:
            log.error('unable to import drmaa. jobs must be run locally.')
            raise e
        
        job_template = session.createJobTemplate()
        
        if self.cross_validation == self.LEAVE_ONE_OUT_CV:
            job_template.remoteCommand = self.leave_one_out_path
        else:
            job_template.remoteCommand = self.svmtrain_path
        
        job_template.args = self.generate_train_args()
        
        job_template.workingDirectory = os.getcwd()
        job_template.output_path = ':' + os.path.join(drmaa.JobTemplate.WORKING_DIRECTORY, output_basename + '.svmout')
        job_template.error_path = ':' + os.path.join(drmaa.JobTemplate.WORKING_DIRECTORY, output_basename + '.svmerr')
        
        job_template.nativeSpecification = self.native_sepcifications
        job_template.environment = self.job_environment
        
        return job_template
        
    def run_drmaa_train(session):
        '''
        Runs a DRMAA job on the passed session. Returns the job id.
        '''
        job_template = self.setup_drmaa_job(session)
        return session.runJob(job_template)

    def generate_train_args():
        '''
        Generates the arguments sutiable for either svm-train or leave_one_out_svm.py
        '''
        if not self.c or not self.training_file or not self.kernel:
            raise ValueError('c, training_file and kernel path must all be set.')
        
        if self.cross_validation == self.LEAVE_ONE_OUT_CV:
            return [self.training_file, '-c', '%f' % c,
                                        '-k', 'openkernel',
                                        '-K', self.kernel_path]
        else type(self.cross_validation) == int:
            return ['-c', '%f' % c,
                    '-k', 'openkernel',
                    '-K', self.kernel_path,
                    '-v', '%i' % self.cross_validation,
                    self.training_file]
        else:
            # just train the data, without any validation
            return ['-c', '%f' % c,
                    '-k', 'openkernel',
                    '-K', self.kernel_path,
                    self.training_file]
    
    def get_accuracy():
        '''
        Parses the output from either the svm-train cross validation or
        leave_one_out_svm.py. Returns a float [0,1].
        '''
        
        if self.cross_validation == self.LEAVE_ONE_OUT_CV:
            lines = open(self.output_basename + '.svmout').readlines()
            
            regex = re.compile('\((\d*\.\d*)% accuracy\)')
            
            accuracy_str = regex.findall('\n'.join(lines))[0]
            return float(accuracy_str)
        else if self.cross_validation:
            svmout_file = open(self.output_basename + '.svmout')
            
            for line in open(svmout_file):
                if line.startswith('Cross Validation Accuracy'):
                    return float(line.split(' ')[-1][:-1])
        
