import abc
import tensorflow as tf
from tf_encrypted.operations.secure_random import seed, seeded_random_uniform
from tf_encrypted.tensor.helpers import inverse
import numpy as np
from .tensor import Tensor
from .fixed import Fixed10, Fixed16
from .ops import *
from .types import Dtypes

maxval = 9223372036854775807
minval = -9223372036854775808
dtype = tf.int64
modulus = 18446744073709551616


def encode(value, base, exp):
    return value * (base ** exp)


def decode(value, base, exp):
    return value / (base ** exp)


def truncate(value):
    player0, player1, player2 = value.players

    x_on_0, x_on_1, x_on_2 = value.shares
    precision_fractional = x_on_0[1].precision_fractional

    with tf.device(player0.device_name):
        s = seed()
        r0 = seeded_random_uniform(value.shape, dtype=dtype, seed=s, minval=minval, maxval=maxval)
        z2_on_0 = r0
        z1_on_0 = tf.bitwise.right_shift(x_on_0[1] + x_on_0[2], precision_fractional) - r0

    with tf.device(player1.device_name):
        r1 = seeded_random_uniform(value.shape, dtype=dtype, seed=s, minval=minval, maxval=maxval)
        z2_on_1 = r1
        z0_on_1 = tf.bitwise.right_shift(x_on_1[0], precision_fractional)

    with tf.device(player2.device_name):
        z0_on_2 = tf.bitwise.right_shift(x_on_2[0], precision_fractional)
        z1_on_2 = z1_on_0

    z_on_0 = (None, z1_on_0, z2_on_0)
    z_on_1 = (z0_on_1, None, z2_on_1)
    z_on_2 = (z0_on_2, z1_on_2, None)
    shares = (z_on_0, z_on_1, z_on_2)

    return ReplicatedPrivate(players, shares)


def zero_share(players, shape):
    player1, player2, player3 = players

    with tf.device(player3.device_name):
        s2 = seed()

    with tf.device(player2.device_name):
        s1 = seed()
        alpha1 = seeded_random_uniform(shape, dtype=dtype, seed=s1, minval=minval, maxval=maxval) - \
            seeded_random_uniform(shape, dtype=dtype, seed=s2, minval=minval, maxval=maxval)

    with tf.device(player1.device_name):
        s0 = seed()
        alpha0 = seeded_random_uniform(shape, dtype=dtype, seed=s0, minval=minval, maxval=maxval) - \
            seeded_random_uniform(shape, dtype=dtype, seed=s1, minval=minval, maxval=maxval)

    with tf.device(player3.device_name):
        alpha2 = seeded_random_uniform(shape, dtype=dtype, seed=s2, minval=minval, maxval=maxval) - \
            seeded_random_uniform(shape, dtype=dtype, seed=s0, minval=minval, maxval=maxval)

    return alpha0, alpha1, alpha2


def share(players, x):
    alpha0, alpha1, alpha2 = zero_share(players, x.shape)

    x1 = alpha1
    x2 = alpha2

    with tf.device(players[0].device_name):
        try:
            x0 = x.backing + alpha0
        except AttributeError:
            x0 = x + alpha0

    # TODO Dtypes to type lookup?
    if x.dtype is Dtypes.FIXED10:
        x0 = Fixed10(x0)
        x1 = Fixed10(x1)
        x2 = Fixed10(x2)
    elif x.dtype is Dtypes.FIXED16:
        x0 = Fixed16(x0)
        x1 = Fixed16(x1)
        x2 = Fixed16(x2)

    xs = ReplicatedPrivate(players, ((None, x1, x2), (x0, None, x2), (x0, x1, None)))

    return xs


def recombine(players, z):
    with tf.device(players[0].device_name):
        final = z.shares[2][0] + z.shares[0][1] + z.shares[1][2]

    return final


# TODO Subclass ProtocolTensor?
class ReplicatedPrivate():
    def __init__(self, players, shares):
        self.players = players
        self.shares = shares

        for share in self.shares[0]:
            if share is not None:
                self._shape = share.shape
                self._base_dtype = share.dtype
                break

    @property
    def dtype(self):
        return (Dtypes.REPLICATED3, self._base_dtype)

    @property
    def shape(self):
        return self._shape

    @property
    def backing(self):
        return self.shares


# TODO benefits of a bass class??
class Kernel:
    def __call__(self, *args):
        pass


class AddPrivatePrivate(Kernel):
    op = Add

    def __call__(self, context, x, y):
        players = x.players

        player0, player1, player2 = players

        x_on_0, x_on_1, x_on_2 = x.shares
        y_on_0, y_on_1, y_on_2 = y.shares

        with tf.device(player0.device_name):
            z1_on_0 = x_on_0[1] + y_on_0[1]
            z2_on_0 = x_on_0[2] + y_on_0[2]

        with tf.device(player1.device_name):
            z0_on_1 = x_on_1[0] + y_on_1[0]
            z2_on_1 = x_on_1[2] + y_on_1[2]

        with tf.device(player2.device_name):
            z0_on_2 = x_on_2[0] + y_on_2[0]
            z1_on_2 = x_on_2[1] + y_on_2[1]

        z_on_0 = (None, z1_on_0, z2_on_0)
        z_on_1 = (z0_on_1, None, z2_on_1)
        z_on_2 = (z0_on_2, z1_on_2, None)
        shares = (z_on_0, z_on_1, z_on_2)

        return ReplicatedPrivate(players, shares)


class SubPrivatePrivate(Kernel):
    op = Sub

    def __call__(self, context, x, y):
        players = x.players
        player0, player1, player2 = players

        x_on_0, x_on_1, x_on_2 = x.shares
        y_on_0, y_on_1, y_on_2 = y.shares

        with tf.device(player0.device_name):
            z1_on_0 = x_on_0[1] - y_on_0[1]
            z2_on_0 = x_on_0[2] - y_on_0[2]

        with tf.device(player1.device_name):
            z0_on_1 = x_on_1[0] - y_on_1[0]
            z2_on_1 = x_on_1[2] - y_on_1[2]

        with tf.device(player2.device_name):
            z0_on_2 = x_on_2[0] - y_on_2[0]
            z1_on_2 = x_on_2[1] - y_on_2[1]

        z_on_0 = (None, z1_on_0, z2_on_0)
        z_on_1 = (z0_on_1, None, z2_on_1)
        z_on_2 = (z0_on_2, z1_on_2, None)
        shares = (z_on_0, z_on_1, z_on_2)

        return ReplicatedPrivate(players, shares)


class MulPrivatePrivate(Kernel):
    op = Mul

    def __call__(self, context, x, y):
        players = x.players
        player0, player1, player2 = players

        x_on_0, x_on_1, x_on_2 = x.shares
        y_on_0, y_on_1, y_on_2 = y.shares

        # get the next zero triple defined by seeds (s0, s1, s2) shared between the three players
        alpha0, alpha1, alpha2 = zero_share(players, x.shape)

        if x._base_dtype is Dtypes.FIXED10:
            alpha0 = Fixed10(alpha0)
            alpha1 = Fixed10(alpha1)
            alpha2 = Fixed10(alpha2)
        elif x._base_dtype is Dtypes.FIXED16:
            alpha0 = Fixed16(alpha0)
            alpha1 = Fixed16(alpha1)
            alpha2 = Fixed16(alpha2)

        with tf.device(player0.device_name):
            z2_on_0 = (x_on_0[2] * y_on_0[2]
                       + x_on_0[2] * y_on_0[1]
                       + x_on_0[1] * y_on_0[2])
            z2_on_1 = z2_on_0 + alpha0

        with tf.device(player1.device_name):
            z0_on_1 = (x_on_1[0] * y_on_1[0]
                       + x_on_1[0] * y_on_1[2]
                       + x_on_1[2] * y_on_1[0])
            z0_on_2 = z0_on_1 + alpha1

        with tf.device(player2.device_name):
            z1_on_2 = (x_on_2[1] * y_on_2[1]
                       + x_on_2[1] * y_on_2[0]
                       + x_on_2[0] * y_on_2[1])
            z1_on_0 = z1_on_2 + alpha2

        z0 = (None, z1_on_0, z2_on_0)
        z1 = (z0_on_1, None, z2_on_1)
        z2 = (z0_on_2, z1_on_2, None)
        shares = (z0, z1, z2)

        if x._base_dtype is Dtypes.FIXED10 or x._base_dtype is Dtypes.Fixed16:
            return truncate(ReplicatedPrivate(players, shares))

        return ReplicatedPrivate(players, shares)


class CastIntReplicated3(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        return share(players, value)

# TODO parameraterized this class to determine encode width


class CastFloat32Fixed16(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        fixed = tf.cast(encode(value, Fixed16.base, Fixed16.precision_fractional), tf.int64)

        return Fixed16(fixed)


class CastFloat32Fixed10(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        fixed = tf.cast(encode(value, Fixed10.base, Fixed10.precision_fractional), tf.int64)

        return Fixed10(fixed)


class CastReplicated3Int(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        return recombine(players, value)


class CastFixed10Float32(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        return decode(value.backing, Fixed10.base, Fixed10.precision_fractional)


class CastFixed16Float32(Kernel):
    op = Cast

    def __call__(self, context, value, dtype, players=None):
        return decode(value.backing, Fixed16.base, Fixed16.precision_fractional)
