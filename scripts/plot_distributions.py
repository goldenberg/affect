#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-06-12.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

import sys
import optparse
import logging
import Gnuplot
import numpy as np

import pdb
logging.basicConfig(level=logging.DEBUG)

help_message = '''
Takes as input an svm file whose vectors contain means and variances. Assumes
that the data came from a Gaussian distribution and plots these Gaussian
distributions using gnuplot. Indices should be 1-indexed.
'''

def main():
    usage = """%prog SVM_FILE [options]"""
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-v", "--verbose", action="store_true", 
                       default=False, dest="verbose")
    
    options, arguments = opt_parser.parse_args()
    
    if len(arguments) != 3:
        logging.error("There should be 3 arguments, the file, mean index and variance index")
        exit()
    
    svm_filename = arguments[0]
    
    distribution_dicts = read_svm_file(svm_filename)
    
    plot_distributions(distribution_dicts)

def read_svm_file(filename):
    '''
    Returns a list of dicts with three keys: 'class', 'mean', 'variance'
    '''
    dicts = []
    for line in open(filename):
        if line.strip() != '':
            fields = line.split(' ')
            
            new_dict = {}
            new_dict['class'] = fields[0]
            
            vector = [float(x.split(':')[1]) for x in fields[1:]]
            
            new_dict['mean']     = vector[0]
            new_dict['min']      = vector[1]
            new_dict['max']      = vector[2]
            new_dict['variance'] = vector[3]
            
            dicts.append(new_dict)
    
    return dicts

def plot_distributions(dist_dicts):
    '''
    Creates a plot with all of the distributions overlayed with different
    classes as different colors.
    '''
    plot_cmd = "plot 1/sqrt(%(variance)f * 2 * pi) * exp(- (x-%(mean)f)**2 / (2 * %(variance)f)) linetype %(class)s;\n"
    
    min_mean = 99999
    max_mean = 0
    
    g = Gnuplot.Gnuplot(debug=1)
    g.title('Distributions')
    g('set data style linespoints')
    g('set yrange [0:.1]')
    g('set xrange [130:180]')
    g('set key off')
    g('set ylabel "probability"')
    g('set xlabel "pitch"')
    for index, dist_dict in enumerate(dist_dicts):
        # start replotting
        if index == 1:
            plot_cmd = 're' + plot_cmd
            
        g(plot_cmd % dist_dict)
        
        min_mean = min(min_mean, dist_dict['mean'])
        max_mean = max(max_mean, dist_dict['mean'])
    
    #g.set_range('xrange', (min_mean-1, max_mean+1))
    #g('set xrange [%f:%f]' % (min_mean, max_mean))
    
def gaussian_pdf(mean, variance, x):
    '''
    Computes the value of a gaussian pdf with specified mean and variance
    at x.
    '''
    return (1 / np.sqrt(variance * 2 * np.pi) ) * np.exp( - (x - mean)^2/(2 * variance))
    
if __name__ == "__main__":
    main()
