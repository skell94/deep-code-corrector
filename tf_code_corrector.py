""" TF Code Corrector Implementation """
import tensorflow as tf
import numpy as np
import random
import os

from models.train_model import TrainModel
from models.evaluation_model import EvaluationModel

tf.app.flags.DEFINE_string("data_directory", "", "Directory of the data set")
tf.app.flags.DEFINE_string("output_directory", "", "Output directory for checkpoints and tests")
tf.app.flags.DEFINE_integer("max_sequence_length", 200, "Max length of input sequence")
tf.app.flags.DEFINE_integer("pad_id", 128, "Code of padding character")
tf.app.flags.DEFINE_integer("sos_id", 2, "Code of start-of-sequence character")
tf.app.flags.DEFINE_integer("eos_id", 3, "Code of end-of-sequence character")
tf.app.flags.DEFINE_integer("batch_size", 128, "Bath size for training input")
tf.app.flags.DEFINE_integer("num_layers", 2, "Number of layers of the network")
tf.app.flags.DEFINE_integer("num_units", 256, "Number of units in each layer")
tf.app.flags.DEFINE_integer("num_iterations", 12000, "Number of iterations in training")
tf.app.flags.DEFINE_integer("eval_steps", 1000, "Step size for evaluation")
tf.app.flags.DEFINE_float("max_gradient_norm", 5.0, "Clip gradients to this norm")
tf.app.flags.DEFINE_float("learning_rate", 0.001, "Learning rate for the optimizer")

FLAGS = tf.app.flags.FLAGS

def main(_):
    if not os.path.exists(FLAGS.output_directory):
        os.makedirs(FLAGS.output_directory)

    train_graph = tf.Graph()
    eval_graph = tf.Graph()

    with train_graph.as_default():
        train_iterator, train_file = create_iterator()
        train_model = TrainModel(FLAGS, train_iterator)
        initializer = tf.global_variables_initializer()

    with eval_graph.as_default():
        eval_iterator, eval_file = create_iterator()
        eval_model = EvaluationModel(FLAGS, eval_iterator)

    train_sess = tf.Session(graph=train_graph)
    eval_sess = tf.Session(graph=eval_graph)

    train_sess.run(initializer)
    initialize_iterator(train_iterator, train_file, 'trainJava.csv', train_sess)
    initialize_iterator(eval_iterator, eval_file, 'testJava.csv', eval_sess)

    for i in range(FLAGS.num_iterations):
        trained = False
        while(not trained):
            try:
                train_model.train(train_sess, i+1)
                trained = True
            except tf.errors.OutOfRangeError:
                initialize_iterator(train_iterator, train_file, 'trainJava.csv', train_sess)


        if (i+1) % FLAGS.eval_steps == 0:
            checkpoint_path = train_model.saver.save(train_sess, FLAGS.output_directory, global_step=i+1)
            eval_model.saver.restore(eval_sess, checkpoint_path)
            evaluated = False
            while(not evaluated):
                try:
                    eval_model.eval(eval_sess)
                    evaluated = True
                except tf.errors.OutOfRangeError:
                    initialize_iterator(eval_iterator, eval_file, 'testJava.csv', eval_sess)


def initialize_iterator(iterator, file_placeholder, projects_file, sess):
    with open(os.path.join(FLAGS.data_directory, projects_file), 'r') as project_data:
        projects = np.array(project_data.read().splitlines())
        project = projects[random.randint(0, len(projects)-1)]
        project = os.path.join(FLAGS.data_directory, project+'.java')

    sess.run(iterator.initializer, feed_dict={file_placeholder: project})

def create_iterator():
    java_file = tf.placeholder(tf.string, shape=[])

    def map_function(line):
        def transform_string(s):
            s = s.strip()
            if random.random() > 0.9 and len(s) > 1:
                brackets = ['(', ')', '[', ']', '{', '}']
                bracket_indices = [i for i, c in enumerate(s) if c in brackets]
                if bracket_indices:
                    drop_index = random.choice(bracket_indices)
                    s = s[:drop_index] + s[drop_index+1:]
            if random.random() > 0.9 and len(s) > 1:
                semicolon_indices = [i for i, c in enumerate(s) if c == ';']
                if semicolon_indices:
                    drop_index = random.choice(semicolon_indices)
                    s = s[:drop_index] + s[drop_index+1:]
            if random.random() > 0.9 and len(s) > 1:
                change_char = random.randint(0, len(s)-2)
                s = s[:change_char] + s[change_char+1] + s[change_char] + s[change_char+2:]
            return s

        t = tf.py_func(lambda string: string.strip(), [line], tf.string)
        t = tf.map_fn(lambda elem:
                tf.py_func(lambda char: np.array(ord(char), dtype=np.int32), [elem], tf.int32), tf.string_split([t], '').values, tf.int32)
        dec_inp = tf.concat([[FLAGS.sos_id], t], 0)
        dec_out = tf.concat([t, [FLAGS.eos_id]], 0)

        enc_inp = t = tf.py_func(transform_string, [line], tf.string)
        enc_inp = tf.map_fn(lambda elem:
                tf.py_func(lambda char: np.array(ord(char), dtype=np.int32), [elem], tf.int32), tf.string_split([enc_inp], '').values, tf.int32)

        return enc_inp, tf.expand_dims(tf.size(enc_inp), 0), dec_inp, dec_out, tf.expand_dims(tf.size(dec_inp),0)


    with tf.device('/cpu:0'):
        dataset = tf.data.TextLineDataset(java_file).filter(lambda line:
                                    tf.logical_and(
                                        tf.not_equal(
                                            tf.size(tf.string_split([tf.py_func(lambda l: l.strip(), [line], tf.string)],"")),
                                            tf.constant(0, dtype=tf.int32)
                                        ),
                                        tf.less(
                                            tf.size(tf.string_split([tf.py_func(lambda l: l.strip(), [line], tf.string)],"")),
                                            tf.constant(FLAGS.max_sequence_length, dtype=tf.int32)
                                        )
                                    )
                               )
        dataset = dataset.shuffle(10000)
        dataset = dataset.map(map_function, num_parallel_calls = 4)
        pad = tf.constant(FLAGS.pad_id, dtype=tf.int32)
        dataset = dataset.apply(tf.contrib.data.padded_batch_and_drop_remainder(
                                    FLAGS.batch_size,
                                    padded_shapes=([None], [1], [None], [None], [1]),
                                    padding_values=(pad, tf.constant(0, dtype=tf.int32), pad, pad, tf.constant(0, dtype=tf.int32))))
        dataset = dataset.prefetch(FLAGS.batch_size)
        return dataset.make_initializable_iterator(), java_file


if __name__ == "__main__":
    tf.app.run()
