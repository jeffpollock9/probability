# Copyright 2020 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Utilities for distributed testing."""
import os

import tensorflow.compat.v2 as tf

from tensorflow_probability.python.internal import distribution_util
from tensorflow_probability.python.internal import test_util

tf.enable_v2_behavior()
JAX_MODE = False
NUM_DEVICES = 4

if JAX_MODE:
  import jax  # pylint: disable=g-import-not-at-top


class DistributedTest(test_util.TestCase):
  """Sets up distributed devices and sharding."""

  def setUp(self):
    super(DistributedTest, self).setUp()
    if JAX_MODE:
      os.environ['XLA_FLAGS'] = (
          '--xla_force_host_platform_device_count={}'.format(NUM_DEVICES))
      assert jax.device_count() == NUM_DEVICES
      self.key = jax.random.PRNGKey(0)
    else:
      physical_devices = tf.config.experimental.list_physical_devices()

      tf.config.experimental.set_virtual_device_configuration(
          physical_devices[0],
          [tf.config.experimental.VirtualDeviceConfiguration()] * NUM_DEVICES)
      self.strategy = tf.distribute.MirroredStrategy(
          devices=tf.config.list_logical_devices())
      self.key = [0, 0]
    self.axis_name = 'i'

  def per_replica_to_tensor(self, value, axis=0):
    if JAX_MODE:
      # JAX, by default, stacks outputs along the first axis.
      return tf.nest.map_structure(
          lambda v: distribution_util.move_dimension(v, 0, axis), value)
    return tf.nest.map_structure(
        lambda per_replica: tf.stack(per_replica.values, axis=axis), value)

  def strategy_run(self, f, args=(), in_axes=0):
    if JAX_MODE:
      if in_axes is None:
        return jax.pmap(
            lambda _, args: f(*args),
            in_axes=(0, None),
            axis_name=self.axis_name)(tf.ones(NUM_DEVICES), args)
      return jax.pmap(f, axis_name=self.axis_name, in_axes=in_axes)(*args)
    return self.strategy.run(tf.function(f, autograph=False), args)

  def shard_values(self, values, axis=0):
    self.assertEqual(values.shape[axis], NUM_DEVICES)

    if JAX_MODE:
      return values

    values = distribution_util.move_dimension(values, axis, 0)

    def value_fn(ctx):
      return values[ctx.replica_id_in_sync_group]

    return self.strategy.experimental_distribute_values_from_function(value_fn)
