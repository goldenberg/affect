def classification_baseline(svm_filename):
    """
    Takes as input an svm filename and returns the baseline for classification
    (the largest class percentage)
    """
    class_sizes = {}
    
    for line in open(svm_filename):
        the_class = line.split(' ')[0]
        
        if the_class not in class_sizes:
            class_sizes[the_class] = 1
        else:
            class_sizes[the_class] += 1
    
    return float(max(class_sizes.values())) / sum(class_sizes.values())

def filter_classes(svm_filename, filtered_svm_filename, classes):
    """
    Reads an svm file and filters out the specified classes.
    """
    svm_in = open(svm_filename)
    svm_out = open(filtered_svm_filename, 'w')
    
    for line in svm_in:
        the_class = line.split(' ')[0]
        
        if the_class in classes or int(the_class) in classes:
            svm_out.write(line)
    
    svm_out.close()

