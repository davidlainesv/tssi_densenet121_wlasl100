import tensorflow as tf
from config import INPUT_HEIGHT, INPUT_WIDTH
from data_augmentation import RandomFlip, RandomScale, RandomShift, RandomRotation, RandomSpeed
from preprocessing import PadIfLessThan, ResizeIfMoreThan, preprocess_dataframe
from skeleton_graph import tssi_v2
from sklearn.preprocessing import OneHotEncoder
import numpy as np
from core import Normalization


available_augmentations = {
    'scale': RandomScale(min_value=-1.0, max_value=1.0, seed=1),
    'shift': RandomShift(min_value=-1.0, max_value=1.0, seed=2),
    'flip': RandomFlip("horizontal", min_value=-1.0, max_value=1.0, seed=3),
    'rotation': RandomRotation(factor=15.0, min_value=-1.0, max_value=1.0, seed=4),
    'speed': RandomSpeed(frames=128, seed=5)
}

augmentations_order_legacy = ['scale', 'shift', 'flip', 'rotation', 'speed']
augmentations_order = ['flip', 'rotation', 'speed']


def dataframe_to_dataset(dataframe, columns, filter_video_ids=[]):
    x_sorted_columns = [col + "_x" for col in columns]
    y_sorted_columns = [col + "_y" for col in columns]

    enc = OneHotEncoder()

    if len(filter_video_ids) > 0:
        dataframe = dataframe[dataframe["video"].isin(filter_video_ids)]

    dataframe_length = dataframe.shape[0]
    num_columns = len(x_sorted_columns)
    stacked_images = np.zeros((dataframe_length, num_columns, 3))
    stacked_images[:, :, 0] = dataframe.loc[:, x_sorted_columns].to_numpy()
    stacked_images[:, :, 1] = dataframe.loc[:, y_sorted_columns].to_numpy()
    video_labels = dataframe.groupby("video")["label"].unique().tolist()
    video_lengths = list(dataframe.groupby("video")["frame"].count())

    X = tf.RaggedTensor.from_row_lengths(
        values=stacked_images, row_lengths=video_lengths)
    y = enc.fit_transform(video_labels).toarray()

    dataset = tf.data.Dataset.from_tensor_slices((X, y))

    return dataset


def generate_train_dataset(dataframe,
                           columns,
                           video_ids,
                           train_map_fn,
                           repeat=False,
                           batch_size=32,
                           buffer_size=5000,
                           deterministic=False):
    # convert dataframe to dataset
    ds = dataframe_to_dataset(dataframe, columns, video_ids)

    # shuffle, map and batch dataset
    if deterministic:
        train_dataset = ds \
            .shuffle(buffer_size) \
            .map(train_map_fn) \
            .batch(batch_size)
    else:
        train_dataset = ds \
            .shuffle(buffer_size) \
            .map(train_map_fn,
                 num_parallel_calls=tf.data.AUTOTUNE,
                 deterministic=False) \
            .batch(batch_size) \
            .prefetch(tf.data.AUTOTUNE)

    if repeat:
        train_dataset = train_dataset.repeat()

    return train_dataset


def generate_test_dataset(dataframe,
                          columns,
                          video_ids,
                          test_map_fn,
                          batch_size=32):
    # convert dataframe to dataset
    ds = dataframe_to_dataset(dataframe, columns, video_ids)

    # batch dataset
    max_element_length = dataframe \
        .groupby("video").size().max()
    bucket_boundaries = list(range(1, max_element_length))
    bucket_batch_sizes = [batch_size] * max_element_length
    ds = ds.bucket_by_sequence_length(
        element_length_func=lambda x, y: tf.shape(x)[0],
        bucket_boundaries=bucket_boundaries,
        bucket_batch_sizes=bucket_batch_sizes,
        no_padding=True)

    # map dataset
    dataset = ds \
        .map(test_map_fn,
             num_parallel_calls=tf.data.AUTOTUNE,
             deterministic=False) \
        .cache()

    return dataset


class Dataset():
    def __init__(self, train_dataframe, validation_dataframe, test_dataframe=None):
        # retrieve the joints order
        _, _, joints_order = tssi_v2()

        # obtain characteristics of the dataset
        num_train_examples = len(train_dataframe["video"].unique())
        num_val_examples = len(validation_dataframe["video"].unique())
        num_total_examples = num_train_examples + num_val_examples
        if test_dataframe is not None:
            num_test_examples = len(test_dataframe["video"].unique())
        else:
            num_test_examples = 0

        # expose variables
        self.joints_order = joints_order
        self.train_dataframe = train_dataframe
        self.validation_dataframe = validation_dataframe
        self.test_dataframe = test_dataframe
        self.num_train_examples = num_train_examples
        self.num_val_examples = num_val_examples
        self.num_test_examples = num_test_examples
        self.num_total_examples = num_total_examples

    def get_training_set(self,
                         batch_size=32,
                         buffer_size=5000,
                         repeat=False,
                         deterministic=False,
                         augmentations=[],
                         normalization=Normalization.Neg1To1):
        # preprocess the train dataframe
        train_dataframe = preprocess_dataframe(self.train_dataframe,
                                               with_root=True,
                                               with_midhip=False,
                                               normalization=normalization)

        # define the length_normalization layers
        train_length_normalization = tf.keras.Sequential([
            PadIfLessThan(frames=INPUT_HEIGHT),
            ResizeIfMoreThan(frames=INPUT_HEIGHT)
        ], name="length_normalization")

        # define the list of augmentations
        # in the default order
        if augmentations == "all":
            augmentations = augmentations_order

        # define the augmentation layers
        # based on the list of augmentations
        layers = [available_augmentations[aug] for aug in augmentations]
        train_augmentation = tf.keras.Sequential(layers, name="augmentation")

        # define the train map function
        @tf.function
        def train_map_fn(x, y):
            batch = tf.expand_dims(x, axis=0)
            batch = train_augmentation(batch, training=True)
            x = train_length_normalization(batch)[0]
            x = tf.ensure_shape(x, [INPUT_HEIGHT, INPUT_WIDTH, 3])
            return x, y

        dataset = generate_train_dataset(train_dataframe,
                                         self.joints_order,
                                         [],
                                         train_map_fn,
                                         repeat=repeat,
                                         batch_size=batch_size,
                                         buffer_size=buffer_size,
                                         deterministic=deterministic)

        return dataset

    def get_validation_set(self,
                           batch_size=32,
                           normalization=Normalization.neg1to1):
        # preprocess the validation dataframe
        val_dataframe = preprocess_dataframe(self.validation_dataframe,
                                             with_root=True,
                                             with_midhip=False,
                                             normalization=normalization)

        # define the preprocessing
        # for the test dataset
        val_preprocessing = tf.keras.Sequential([
            PadIfLessThan(frames=INPUT_HEIGHT)
        ], name="preprocessing")

        # define the train map function
        @tf.function
        def val_map_fn(x, y):
            x = x.to_tensor()
            x = val_preprocessing(x)
            return x, y

        dataset = generate_test_dataset(val_dataframe,
                                        self.joints_order,
                                        [],
                                        val_map_fn,
                                        batch_size=batch_size)

        return dataset

    def get_testing_set(self,
                        batch_size=32,
                        normalization=Normalization.Neg1To1):
        # raise exception if test_dataframe
        # does not exist
        if self.test_dataframe is None:
            raise Exception("Test dataframe was not provided")

        # preprocess the test dataframe
        test_dataframe = preprocess_dataframe(self.test_dataframe,
                                              with_root=True,
                                              with_midhip=False,
                                              normalization=normalization)

        # define the preprocessing
        # for the test dataset
        test_preprocessing = tf.keras.Sequential([
            PadIfLessThan(frames=INPUT_HEIGHT)
        ], name="preprocessing")

        # define the train map function
        @tf.function
        def test_map_fn(x, y):
            x = x.to_tensor()
            x = test_preprocessing(x)
            return x, y

        dataset = generate_test_dataset(test_dataframe,
                                        self.joints_order,
                                        [],
                                        test_map_fn,
                                        batch_size=batch_size)

        return dataset
