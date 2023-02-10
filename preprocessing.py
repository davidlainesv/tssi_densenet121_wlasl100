import tensorflow as tf
import numpy as np
from mediapipe.python.solutions.pose import PoseLandmark
from enum import Enum


class Normalization(str, Enum):
    Neg1To1 = 'neg1_to_1'
    Legacy = 'legacy'


def replace_nan_with_other_column(
        dataframe, source_columns, target_column):
    # array of dataframe at source_columns
    arr = dataframe[source_columns].to_numpy()
    # array of dataframe at target_column
    values = dataframe[target_column].to_numpy()
    # indices where arr is nan
    indices = np.where(np.isnan(arr))
    # replace nan's of arr with values
    for i in range(indices[0].shape[0]):
        row = indices[0][i]
        column = indices[1][i]
        arr[row][column] = values[row]
    # return modified arr
    return arr


def preprocess_dataframe(dataframe, select_columns=[], with_root=True, with_midhip=False):
    dataframe = dataframe.copy()

    # obtain x, y columns
    x_columns = dataframe.columns[3::2]
    y_columns = dataframe.columns[4::2]

    # columns that could have nan values
    x_left_hand_columns = [col for col in x_columns if "leftHand" in col]
    y_left_hand_columns = [col for col in y_columns if "leftHand" in col]
    x_right_hand_columns = [col for col in x_columns if "rightHand" in col]
    y_right_hand_columns = [col for col in y_columns if "rightHand" in col]
    x_face_columns = [col for col in x_columns if "face" in col]
    y_face_columns = [col for col in y_columns if "face" in col]

    # columns with non-nan values
    x_left_wrist_column = 'pose_' + str(int(PoseLandmark.LEFT_WRIST)) + '_x'
    y_left_wrist_column = 'pose_' + str(int(PoseLandmark.LEFT_WRIST)) + '_y'
    x_right_wrist_column = 'pose_' + str(int(PoseLandmark.RIGHT_WRIST)) + '_x'
    y_right_wrist_column = 'pose_' + str(int(PoseLandmark.RIGHT_WRIST)) + '_y'
    x_nose_column = "pose_" + str(int(PoseLandmark.NOSE)) + "_x"
    y_nose_column = "pose_" + str(int(PoseLandmark.NOSE)) + "_y"

    # add root column
    if with_root:
        dataframe['root_x'] = (dataframe['pose_' + str(int(PoseLandmark.LEFT_SHOULDER)) + '_x'] +
                               dataframe['pose_' + str(int(PoseLandmark.RIGHT_SHOULDER)) + '_x']) / 2.
        dataframe['root_y'] = (dataframe['pose_' + str(int(PoseLandmark.LEFT_SHOULDER)) + '_y'] +
                               dataframe['pose_' + str(int(PoseLandmark.RIGHT_SHOULDER)) + '_y']) / 2.

    # add midhip column
    if with_midhip:
        dataframe['midhip_x'] = (dataframe['pose_' + str(int(PoseLandmark.LEFT_HIP)) + '_x'] +
                                 dataframe['pose_' + str(int(PoseLandmark.RIGHT_HIP)) + '_x']) / 2.
        dataframe['midhip_y'] = (dataframe['pose_' + str(int(PoseLandmark.LEFT_HIP)) + '_y'] +
                                 dataframe['pose_' + str(int(PoseLandmark.RIGHT_HIP)) + '_y']) / 2.

    # # replace left hand columns with the left wrist coordinates
    dataframe.loc[:, x_left_hand_columns] = replace_nan_with_other_column(
        dataframe, x_left_hand_columns, x_left_wrist_column)
    dataframe.loc[:, y_left_hand_columns] = replace_nan_with_other_column(
        dataframe, y_left_hand_columns, y_left_wrist_column)

    # # Replace right hand columns with the right wrist coordinates
    dataframe.loc[:, x_right_hand_columns] = replace_nan_with_other_column(
        dataframe, x_right_hand_columns, x_right_wrist_column)
    dataframe.loc[:, y_right_hand_columns] = replace_nan_with_other_column(
        dataframe, y_right_hand_columns, y_right_wrist_column)

    # # replace face columns with the nose coordinates
    dataframe.loc[:, x_face_columns] = replace_nan_with_other_column(
        dataframe, x_face_columns, x_nose_column)
    dataframe.loc[:, y_face_columns] = replace_nan_with_other_column(
        dataframe, y_face_columns, y_nose_column)

    # filter columns
    if len(select_columns) > 0:
        base_columns = list(dataframe.columns[:3])
        unique_columns = list(np.unique(select_columns))
        dataframe = dataframe.loc[:, base_columns + unique_columns]

    return dataframe


def normalize_dataframe(dataframe, normalization=Normalization.Neg1To1):
    if normalization == Normalization.Neg1To1:
        return normalize_dataframe_from_neg1_to_1(dataframe)
    elif normalization == Normalization.Legacy:
        return normalize_dataframe_legacy(dataframe)
    else:
        raise Exception(f"Unknown normalization: {normalization}")


def normalize_dataframe_from_neg1_to_1(dataframe):
    dataframe = dataframe.copy()

    # obtain x, y columns
    x_columns = dataframe.columns[3::2]
    y_columns = dataframe.columns[4::2]
    xy_columns = dataframe.columns[3:]

    # center x, y columns
    root_arr = dataframe[['root_x', 'root_y']].to_numpy()
    dataframe.loc[:, x_columns] = dataframe[x_columns] - \
        root_arr[:, 0][:, None]
    dataframe.loc[:, y_columns] = dataframe[y_columns] - \
        root_arr[:, 1][:, None]

    # scale to (-1, 1)
    xy_data = dataframe[xy_columns]
    scales = xy_data.abs().max(axis=1).to_numpy()[:, np.newaxis]
    dataframe.loc[:, xy_columns] = xy_data / scales

    return dataframe


def normalize_dataframe_legacy(dataframe):
    dataframe = dataframe.copy()
    x_columns = dataframe.columns[3::2]
    y_columns = dataframe.columns[4::2]
    xy_columns = dataframe.columns[3:]

    # Move in the x-axis
    x_smaller_than_0_mask = np.any(
        dataframe[x_columns] < 0, axis=1)
    x_offset = dataframe.loc[x_smaller_than_0_mask, x_columns].min(
        axis=1).abs().values[:, np.newaxis]
    dataframe.loc[x_smaller_than_0_mask,
                  x_columns] = dataframe.loc[x_smaller_than_0_mask, x_columns] + x_offset

    # Move in the y-axis
    y_smaller_than_0_mask = np.any(
        dataframe[y_columns] < 0, axis=1)
    y_offset = dataframe.loc[y_smaller_than_0_mask, y_columns].min(
        axis=1).abs().values[:, np.newaxis]
    dataframe.loc[y_smaller_than_0_mask,
                  y_columns] = dataframe.loc[y_smaller_than_0_mask, y_columns] + y_offset

    # Scale videos outside (0, 1) to (0, 1)
    # out_of_scale_mask = np.any(selected_data > 1, axis=1)
    # out_of_scale_data = selected_data[out_of_scale_mask]
    # scales = out_of_scale_data.max(axis=1).to_numpy()[:, np.newaxis]
    # selected_data.loc[out_of_scale_mask, :] = out_of_scale_data / scales

    out_of_scale_mask = np.any(dataframe[xy_columns] > 1, axis=1)
    abs_grouped = dataframe.loc[out_of_scale_mask, :].abs().groupby("video")
    repetitions = abs_grouped.size().to_numpy()
    max_per_video = abs_grouped[xy_columns].max().max(axis=1).to_numpy()
    max_per_video_repeated = max_per_video.repeat(repetitions)[:, None]
    dataframe.loc[out_of_scale_mask, xy_columns] = \
        dataframe.loc[out_of_scale_mask, xy_columns] / max_per_video_repeated

    return dataframe


def filter_dataframe_by_video_ids(dataframe, video_ids):
    mask = dataframe["video"].isin(video_ids)
    return dataframe.loc[mask, :]


class PadIfLessThan(tf.keras.layers.Layer):
    def __init__(self, frames=128, **kwargs):
        super().__init__(**kwargs)
        self.frames = frames

    @tf.function
    def call(self, images):
        height = tf.shape(images)[1]
        width = tf.shape(images)[2]
        height_pad = tf.math.maximum(0, self.frames - height)
        paddings = [[0, 0], [0, height_pad], [0, 0], [0, 0]]
        padded_images = tf.pad(images, paddings, "CONSTANT")
        return padded_images


class ResizeIfMoreThan(tf.keras.layers.Layer):
    def __init__(self, frames=128, **kwargs):
        super().__init__(**kwargs)
        self.frames = frames

    @tf.function
    def call(self, images):
        height = tf.shape(images)[1]
        width = tf.shape(images)[2]
        new_size = [self.frames, width]
        resized = tf.cond(height > self.frames,
                          lambda: tf.image.resize(images, new_size),
                          lambda: images)
        return resized


class Center(tf.keras.layers.Layer):
    def __init__(self, around_index=0, **kwargs):
        super().__init__(**kwargs)
        self.around_index = around_index

    @tf.function
    def call(self, batch):
        # batch.shape => (examples, frames, joints, coordinates)
        # [color].shape => (examples, frames, joints)
        [red, green, blue] = tf.unstack(batch, axis=-1)

        # [color]_around_joint.shape => (examples, frames, 1)
        red_around_joint = tf.expand_dims(
            red[:, :, self.around_index], axis=-1)
        green_around_joint = tf.expand_dims(
            green[:, :, self.around_index], axis=-1)

        # new_[color].shape => (examples, frames, joints)
        new_red = red - red_around_joint
        new_green = green - green_around_joint

        return tf.stack([new_red, new_green, blue], axis=-1)


class TranslationScaleInvariant(tf.keras.layers.Layer):
    def __init__(self, level='channel', **kwargs):
        super().__init__(**kwargs)
        self.level_dict = {
            'channel': tf.constant(0),
            'joint': tf.constant(1)
        }
        self.level = self.level_dict[level]

    @tf.function
    def channel_level_translation_scale_invariant(self, batch):
        # batch.shape => (examples, frames, joints, coordinates)
        # [color].shape => (examples, frames, joints)
        [red, green, blue] = tf.unstack(batch, axis=-1)

        # [color]_min.shape => (examples, 1, 1)
        red_min = tf.reduce_min(red, axis=[-1, -2], keepdims=True)
        green_min = tf.reduce_min(green, axis=[-1, -2], keepdims=True)
        blue_min = tf.reduce_min(blue, axis=[-1, -2], keepdims=True)

        # [color]_max.shape => (examples, 1, 1)
        red_max = tf.reduce_max(red, axis=[-1, -2], keepdims=True)
        green_max = tf.reduce_max(green, axis=[-1, -2], keepdims=True)
        blue_max = tf.reduce_max(blue, axis=[-1, -2], keepdims=True)

        # new_[color].shape => (examples, frames, joints)
        new_red = tf.math.divide_no_nan((red - red_min), (red_max - red_min))
        new_green = tf.math.divide_no_nan(
            (green - green_min), (green_max - green_min))
        new_blue = tf.math.divide_no_nan(
            (blue - blue_min), (blue_max - blue_min))

        return tf.stack([new_red, new_green, new_blue], axis=-1)

    @tf.function
    def joint_level_translation_scale_invariant(self, batch):
        # batch.shape => (examples, frames, joints, coordinates)
        # [color].shape => (examples, frames, joints)
        [red, green, blue] = tf.unstack(batch, axis=-1)

        # [color]_min.shape => (examples, 1, joints)
        red_min = tf.reduce_min(red, axis=-2, keepdims=True)
        green_min = tf.reduce_min(green, axis=-2, keepdims=True)
        blue_min = tf.reduce_min(blue, axis=-2, keepdims=True)

        # [color]_max.shape => (examples, 1, joints)
        red_max = tf.reduce_max(red, axis=-2, keepdims=True)
        green_max = tf.reduce_max(green, axis=-2, keepdims=True)
        blue_max = tf.reduce_max(blue, axis=-2, keepdims=True)

        # new_[color].shape => (examples, frames, joints)
        new_red = tf.math.divide_no_nan((red - red_min), (red_max - red_min))
        new_green = tf.math.divide_no_nan(
            (green - green_min), (green_max - green_min))
        new_blue = tf.math.divide_no_nan(
            (blue - blue_min), (blue_max - blue_min))

        return tf.stack([new_red, new_green, new_blue], axis=-1)

    @tf.function
    def call(self, batch):
        batch = tf.cond(
            self.level == self.level_dict['channel'],
            lambda: self.channel_level_translation_scale_invariant(batch),
            lambda: self.joint_level_translation_scale_invariant(batch))
        return batch
