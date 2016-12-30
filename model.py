from keras.models import Model
from keras.layers import *
from keras.layers.convolutional import *
from keras.layers.normalization import BatchNormalization
from keras import backend as K

def handle_dim_ordering():
    global ROW_AXIS
    global COL_AXIS
    global CHANNEL_AXIS
    if K.image_dim_ordering() == 'tf':
        ROW_AXIS = 1
        COL_AXIS = 2
        CHANNEL_AXIS = 3
    else:
        CHANNEL_AXIS = 1
        ROW_AXIS = 2
        COL_AXIS = 3

def _bn_relu_conv(nb_filter, nb_row, nb_col, subsample=(1, 1), name=''):
    def f(input):
        norm = BatchNormalization(mode=0, axis=CHANNEL_AXIS, momentum=0.95)(input)
        activation = Activation("relu")(norm)
        return Convolution2D(nb_filter=nb_filter, nb_row=nb_row, nb_col=nb_col, init="he_normal", border_mode="same", subsample=subsample, name=name)(activation)
    return f

def _shortcut(input, residual, name=''):
    stride_width = input._keras_shape[ROW_AXIS] // residual._keras_shape[ROW_AXIS]
    stride_height = input._keras_shape[COL_AXIS] // residual._keras_shape[COL_AXIS]
    equal_channels = residual._keras_shape[CHANNEL_AXIS] == input._keras_shape[CHANNEL_AXIS]
    
    shortcut = input
    if stride_width > 1 or stride_height > 1 or not equal_channels:
        shortcut = Convolution2D(nb_filter=residual._keras_shape[CHANNEL_AXIS], nb_row=1, nb_col=1, subsample=(stride_width, stride_height), init="he_normal", border_mode="valid", name='{}_1x1_proj'.format(name))(input)
        # shortcut = BatchNormalization(mode=0, axis=CHANNEL_AXIS, momentum=0.95)(shortcut)

    return merge([shortcut, residual], mode="sum")
    
def bottleneck(nb_filters, init_subsample=(1, 1), name='', isFirst=False):
    def f(input):
        if isFirst:
            init_subsample=(2, 2)
        conv_1_1 = _bn_relu_conv(nb_filters, 1, 1, subsample=init_subsample, name='{}_1x1_reduce'.format(name))(input)
        conv_3_3 = _bn_relu_conv(nb_filters, 3, 3, name='{}_3x3'.format(name))(conv_1_1)
        residual = _bn_relu_conv(nb_filters * 4, 1, 1, name='{}_1x1_increase'.format(name))(conv_3_3)
        return _shortcut(input, residual, name)

    return f

def _dilated_bn_relu_conv(nb_filter, nb_row, nb_col, subsample=(1, 1), atrous_rate=(2,2), name=''):
    def f(input):
        norm = BatchNormalization(mode=0, axis=CHANNEL_AXIS, momentum=0.95)(input)
        activation = Activation("relu")(norm)
        return AtrousConvolution2D(nb_filter=nb_filter, nbrow=nb_row, nb_col, init='he_normal', border_mode='same', subsample=subsample, atrous_rate=(2,2), name=name)(activation)
    return f

def dilated_bottleneck(nb_filters, init_subsample=(1, 1), name='', atrous_rate=(2,2), isFirst=False):
    def f(input):
        if isFirst:
            init_subsample=(2, 2)
        conv_1_1 = _bn_relu_conv(nb_filters, 1, 1, subsample=init_subsample, name='{}_1x1_reduce'.format(name))(input)
        conv_3_3 = _dilated_bn_relu_conv(nb_filters, 3, 3, name='{}_3x3'.format(name), atrous_rate=atrous_rate)(conv_1_1)
        residual = _bn_relu_conv(nb_filters * 4, 1, 1, name='{}_1x1_increase'.format(name))(conv_3_3)
        return _shortcut(input, residual, name)

    return f

def PSPNET(input_shape = None, batch_shape = None):
    handle_dim_ordering()
    if batch_shape:
        img_input = Input(batch_shape = batch_shape)
    else:
        img_input = Input(input_shape = input_shape)
    conv1_1_s2 = Convolution2D(64, 3, 3, init="he_normal", border_mode="same", subsample=(2, 2), name='conv1_1_3x3_s2')(img_input)
    conv1_1_s2_bn = BatchNormalization(mode=0, axis=3, momentum=0.95)(conv1_1_s2)
    conv1_1_s2_bn_ = Activation('relu')(conv1_1_s2_bn)
    # conv1_1_s2_bn_ = ZeroPadding2D(padding=(1, 1))(conv1_1_s2_bn_)
    conv1_2 = Convolution2D(64, 3, 3, init="he_normal", border_mode="same", subsample=(1, 1), name='conv1_2_3x3')(conv1_1_s2_bn)
    conv1_2_bn = BatchNormalization(mode=0, axis=3, momentum=0.95)(conv1_2)
    conv1_2_bn_ = Activation('relu')(conv1_2_bn)
    # conv1_2_bn_ = ZeroPadding2D(padding=(1, 1))(conv1_2_bn_)
    # The valid means there is no padding around input or feature map, while same means there are some padding around input or feature map, making the output feature map's size same as the input's
    conv1_3 = Convolution2D(128, 3, 3, init="he_normal", border_mode="same", subsample=(1, 1), name='conv1_3_3x3')(conv1_2_bn_)
    conv1_3_bn = BatchNormalization(mode=0, axis=3, momentum=0.95)(conv1_3)
    conv1_3_bn_ = Activation('relu')(conv1_3_bn)
    # conv1_3_bn_ = ZeroPadding2D(padding=(1, 1))(conv1_3_bn_)
    pool1 = MaxPooling2D(pool_size=(3, 3), strides=(2, 2), border_mode='same', name='pool1_3x3_s2')(conv1_3_bn_)
    
    conv2_1 = bottleneck(64, name='conv2_1')(pool1)
    conv2_2 = bottleneck(64, name='conv2_2')(conv2_1)
    conv2_3 = bottleneck(64, name='conv2_3')(conv2_2)

    conv3_1 = bottleneck(128, name='conv3_1', isFirst=True)(conv2_3)
    conv3_2 = bottleneck(128, name='conv3_2')(conv3_1)
    conv3_3 = bottleneck(128, name='conv3_3')(conv3_2)
    conv3_4 = bottleneck(128, name='conv3_4')(conv3_3)
    
    
    # conv4_1 = dilated_bottleneck(256, name='conv4_2')(conv4_1)
    conv4_1 = dilated_bottleneck(256, name='conv4_1')(conv3_4)
    conv4_2 = dilated_bottleneck(256, name='conv4_2')(conv4_1)
    conv4_3 = dilated_bottleneck(256, name='conv4_3')(conv4_2)
    conv4_4 = dilated_bottleneck(256, name='conv4_4')(conv4_3)
    conv4_5 = dilated_bottleneck(256, name='conv4_5')(conv4_4)
    conv4_6 = dilated_bottleneck(256, name='conv4_6')(conv4_5)
    conv4_7 = dilated_bottleneck(256, name='conv4_7')(conv4_6)
    conv4_8 = dilated_bottleneck(256, name='conv4_8')(conv4_7)
    conv4_9 = dilated_bottleneck(256, name='conv4_9')(conv4_8)
    conv4_10 = dilated_bottleneck(256, name='conv4_10')(conv4_9)
    conv4_11 = dilated_bottleneck(256, name='conv4_11')(conv4_10)
    conv4_12 = dilated_bottleneck(256, name='conv4_12')(conv4_11)
    conv4_13 = dilated_bottleneck(256, name='conv4_13')(conv4_12)
    conv4_14 = dilated_bottleneck(256, name='conv4_14')(conv4_13)
    conv4_15 = dilated_bottleneck(256, name='conv4_15')(conv4_14)
    conv4_16 = dilated_bottleneck(256, name='conv4_16')(conv4_15)
    conv4_17 = dilated_bottleneck(256, name='conv4_17')(conv4_16)
    conv4_18 = dilated_bottleneck(256, name='conv4_18')(conv4_17)
    conv4_19 = dilated_bottleneck(256, name='conv4_19')(conv4_18)
    conv4_20 = dilated_bottleneck(256, name='conv4_20')(conv4_19)
    conv4_21 = dilated_bottleneck(256, name='conv4_21')(conv4_20)
    conv4_22 = dilated_bottleneck(256, name='conv4_22')(conv4_21)
    conv4_23 = dilated_bottleneck(256, name='conv4_23')(conv4_22)
    conv4_24 = dilated_bottleneck(256, name='conv4_24')(conv4_23)

    conv5_1 = dilated_bottleneck(512, name='conv5_1', atrous_rate=(4,4))(conv4_24) 
    conv5_2 = dilated_bottleneck(512, name='conv5_2', atrous_rate=(4,4))(conv5_1)
    conv5_3 = dilated_bottleneck(512, name='conv5_3', atrous_rate=(4,4))(conv5_2)
    
    conv5_3_pool1 = AveragePooling2D(pool_size=(60, 60), strides=60, border_mode='same')(conv5_3)
    conv5_3_pool1_conv = _bn_conv_relu(512, 1, 1, name='conv5_3_pool1_conv')
     
