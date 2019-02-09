# Copyright 2018 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
.. _tf_qnode:

TensorFlow eager interface
**************************

**Module name:** :mod:`pennylane.interfaces.tfe`

.. currentmodule:: pennylane.interfaces.tfe

.. warning:: This interface is **experimental**


Using the TensorFlow interface
------------------------------

.. note::

    To use the TensorFlow eager execution interface in PennyLane, you must first install TensorFlow.

    This interface **only** supports TensorFlow in eager execution mode! This can be set
    by running the following commands at the beginning of your PennyLane script/program:

    >>> import tensorflow as tf
    >>> import tensorflow.contrib.eager as tfe
    >>> tf.enable_eager_execution()

Using the TensorFlow eager execution interface is easy in PennyLane --- let's consider a few ways
it can be done.


Via the QNode decorator
^^^^^^^^^^^^^^^^^^^^^^^

The :ref:`QNode decorator <qnode_decorator>` is the recommended way for creating QNodes
in PennyLane. The only change required to construct a TensorFlow-capable QNode is to
specify the ``interface='tfe'`` keyword argument:

.. code-block:: python

    dev = qml.device('default.qubit', wires=2)

    @qml.qnode(dev, interface='tfe')
    def circuit(phi, theta):
        qml.RX(phi[0], wires=0)
        qml.RY(phi[1], wires=1)
        qml.CNOT(wires=[0, 1])
        qml.PhaseShift(theta, wires=0)
        return qml.expval.PauliZ(0), qml.expval.Hadamard(1)

The QNode ``circuit()`` is now a TensorFlow-capable QNode, accepting ``tfe.Variable`` objects
as input, and returning ``tf.Tensor`` objects.

>>> phi = tfe.Variable([0.5, 0.1])
>>> theta = tfe.Variable(0.2)
>>> circuit(phi, theta)
<tf.Tensor: id=22, shape=(2,), dtype=float64, numpy=array([ 0.87758256,  0.68803733])>


Via the QNode class
^^^^^^^^^^^^^^^^^^^

Sometimes, it is more convenient to instantiate a :class:`~.QNode` object directly, for example,
if you would like to reuse the same quantum function across multiple devices, or even
using different classical interfaces:

.. code-block:: python

    dev1 = qml.device('default.qubit', wires=2)
    dev2 = qml.device('forest.wavefunction', wires=2)

    def circuit(phi, theta):
        qml.RX(phi[0], wires=0)
        qml.RY(phi[1], wires=1)
        qml.CNOT(wires=[0, 1])
        qml.PhaseShift(theta, wires=0)
        return qml.expval.PauliZ(0), qml.expval.Hadamard(1)

    qnode1 = qml.QNode(circuit, dev1)
    qnode2 = qml.QNode(circuit, dev2)

We can convert the default NumPy-interfacing QNode to a TensorFlow-interfacing QNode by
using the :meth:`~.QNode.to_tf` method:

>>> qnode1 = qnode1.to_tfe()
>>> qnode1
<function pennylane.interfaces.tfe.custom_gradient.<locals>.decorated(*input_)>

Internally, the :meth:`~.QNode.to_tfe` method uses the :func:`~.TFEQNode` function
to do the conversion.


Quantum gradients using TensorFlow
----------------------------------

Since a TensorFlow-interfacing QNode acts like any other TensorFlow function,
the standard method used to calculate gradients in eager mode with TensorFlow can be used.

For example:

.. code-block:: python

    dev = qml.device('default.qubit', wires=2)

    @qml.qnode(dev, interface='tfe')
    def circuit(phi, theta):
        qml.RX(phi[0], wires=0)
        qml.RY(phi[1], wires=1)
        qml.CNOT(wires=[0, 1])
        qml.PhaseShift(theta, wires=0)
        return qml.expval.PauliZ(0)

    phi = tfe.Variable([0.5, 0.1])
    theta = tfe.Variable(0.2)

    grad_fn = tfe.implicit_value_and_gradients(circuit)
    result, [(phi_grad, phi_var), (theta_grad, theta_var)] = grad_fn(phi, theta)

Now, printing the gradients:

>>> phi_grad
array([-0.47942549,  0.        ])
>>> theta_grad
-5.5511151231257827e-17

.. _pytf_optimize:

Optimization using TensorFlow
-----------------------------



Code details
^^^^^^^^^^^^
"""
# pylint: disable=redefined-outer-name
import numpy as np
import tensorflow as tf
import tensorflow.contrib.eager as tfe # pylint: disable=unused-import

from pennylane.utils import unflatten


def TFEQNode(qnode):
    """Function that accepts a :class:`~.QNode`, and returns a TensorFlow eager execution-compatible QNode.

    Args:
        qnode (~pennylane.qnode.QNode): a PennyLane QNode

    Returns:
        function: the QNode as a TensorFlow function
    """
    @tf.custom_gradient
    def _TFEQNode(*input_):
        # detach all input Tensors, convert to NumPy array
        args = [i.numpy() if isinstance(i, (tf.Variable, tf.Tensor)) else i for i in input_]
        # if NumPy array is scalar, convert to a Python float
        args = [i.tolist() if (isinstance(i, np.ndarray) and not i.shape) else i for i in args]

        # evaluate the QNode
        res = qnode(*args)

        if not isinstance(res, np.ndarray):
            # scalar result, cast to NumPy scalar
            res = np.array(res)

        def grad(grad_output):
            """Returns the vector-Jacobian product"""
            # evaluate the Jacobian matrix of the QNode
            jacobian = qnode.jacobian(args)

            grad_output_np = grad_output.numpy()

            # perform the vector-Jacobian product
            if not grad_output_np.shape:
                temp = grad_output_np * jacobian
            else:
                temp = grad_output_np.T @ jacobian

            # restore the nested structure of the input args
            grad_input = unflatten(temp.flat, args)
            return tuple(grad_input)

        return res, grad

    return _TFEQNode
