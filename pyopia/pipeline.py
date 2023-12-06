'''
Module for managing the PyOpia processing pipeline

Refer to :class:`Pipeline` for examples of how to process datasets and images
'''
from typing import TypedDict
import datetime
import pandas as pd
from operator import methodcaller
import toml
import sys
import importlib
from skimage.io import imread


class Pipeline():
    '''The processing pipeline class
    ================================

    The classes called in the Pipeline steps can be modified, and the names of the steps changed.
    New steps can be added or deleted as required.

    The classes called in the Pipeline steps need to take a TOML-formatted dictionary as input
    and return a dictionary of data as output.
    This common data dictionary: :class:`pyopia.pipeline.Data` is therefore passed between steps so that data
    or variables generated by each step can be passed along the pipeline.

    By default, the step names: `initial`, `classifier`, and `createbackground`
    are run when initialising `Pipeline`.
    The remaining steps will be run on Pipeline.run().
    You can add initial steps with the optional input `initial_steps`,
    which takes a list of strings of the step key names that should only be run on initialisation of the pipeline.
    i.e.: `processing_pipeline = pyopia.pipeline.Pipeline(toml_settings, initial_steps=['classifier', 'novel_initial_process'])`

    The step called 'classifier' must return a dict containing:
    :attr:`pyopia.pipeline.Data.cl` in order to run successfully.

    Running a pipeline:
    """""""""""""""""""

    `Pipeline.run()` takes a string as input.
    This string is put into the `data` dict available to the steps in the pipeline as `data['filename']`.
    This is intended for use in looping through several files during processing, so run can be
    called multiple times with different filenames.

    Examples of setting up and running a pipeline,
    can be found for SilCam `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/pipeline-holo.ipynb>`_,
    and holographic analysis `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/pipeline-holo.ipynb>`_.

    Example config files can be found for SilCam `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/config.toml>`_,
    and for holographic analysis `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/config-holo.toml>`_.

    You can check the workflow used by reading the steps from the metadata in the
    output file using :func:`pyopia.pipeline.steps_from_xstats`

    More examples and guides can be found on the `PyOIA By Example <https://pyopia.readthedocs.io/en/latest/examples.html>`_ page.
    '''

    def __init__(self, settings,
                 initial_steps=['initial', 'classifier', 'createbackground']):

        self.settings = settings
        self.stepnames = list(settings['steps'].keys())

        self.initial_steps = initial_steps
        print('Initialising pipeline')
        self.data = Data()
        self.data['cl'] = None
        self.data['settings'] = settings

        self.pass_general_settings()
        print('raw_files:', self.data['raw_files'])

        for stepname in self.stepnames:
            if not self.initial_steps.__contains__(stepname):
                continue
            if stepname == 'classifier':
                callobj = self.step_callobj(stepname)
                self.data['cl'] = callobj()
            else:
                callobj = self.step_callobj(stepname)
                self.data = callobj(self.data)

        print('Pipeline ready with these data: ', list(self.data.keys()))

    def run(self, filename):
        '''Method for executing the processing pipeline.

        Args:
            filename (str): file to be processed

        Returns:
            stats (DataFrame): stats DataFrame of particle statistics associated with 'filename'

        Note: the returned stats from this function are single-image only and not appended
        if you loop through several filenames! It is recommended to use this step in the pipeline
        for properly appending data into NetCDF format when processing several files.

        .. code-block:: python

            [steps.output]
            pipeline_class = 'pyopia.io.StatsDisc'
            output_datafile = 'proc/test'  # prefix path for output nc file
        '''

        self.data['filename'] = filename

        for stepname in self.stepnames:
            if self.initial_steps.__contains__(stepname):
                continue

            callobj = self.step_callobj(stepname)
            self.data = callobj(self.data)

        stats = self.data['stats']

        return stats

    def step_callobj(self, stepname):

        pipeline_class = self.settings['steps'][stepname]['pipeline_class']
        classname = pipeline_class.split('.')[-1]
        modulename = pipeline_class.replace(classname, '')[:-1]

        keys = [k for k in self.settings['steps'][stepname] if k != 'pipeline_class']

        arguments = dict()
        for k in keys:
            arguments[k] = self.settings['steps'][stepname][k]

        m = methodcaller(classname, **arguments)
        callobj = m(sys.modules[modulename])
        print(classname, ' ready with:', arguments, ' and data', self.data.keys())
        return callobj

    def pass_general_settings(self):
        self.data['raw_files'] = self.settings['general']['raw_files']

    def print_steps(self):
        '''Print the steps dictionary
        '''

        # an eventual metadata parser could replace this below printing
        # and format into an appropriate standard
        print('\n-- Pipeline configuration --\n')
        from pyopia import __version__ as pyopia_version
        print('PyOpia version: ' + pyopia_version + '\n')
        print(steps_to_string(self.steps))
        print('\n---------------------------------\n')


class Data(TypedDict):
    '''Data dictionary which is passed between :class:`pyopia.pipeline` steps.

    For debugging, you can use :class:`pyopia.pipeline.ReturnData`
    at the end of a steps dictionary to return of this Data dictionary
    for exploratory purposes.

    In future this may be better as a data class with slots (from python 3.10).

    This is an example of a link to the imc key doc:
    :attr:`pyopia.pipeline.Data.imc`
    '''

    raw_files: str
    '''String used by glob to obtain file list of data to be processed
    This is exracted automatically from 'general.raw_files' in the toml config
    during pipeline initialisation.
    '''
    imraw: float
    '''Raw uncorrected image'''
    img: float
    '''Raw uncorrected image. To be deprecatied and changed to imraw'''
    imc: float
    '''Single composite image of focussed particles ready for segmentation
    Obtained from e.g. :class:`pyopia.background.CorrectBackgroundAccurate`
    '''
    bgstack: float
    '''List of images making up the background (either static or moving)
    Obtained from :class:`pyopia.background.CreateBackground`
    '''
    imbg: float
    '''Background image that can be used to correct :attr:`pyopia.pipeline.Data.imraw`
    and calcaulte :attr:`pyopia.pipeline.Data.imc`
    Obtained from :class:`pyopia.background.CreateBackground`
    '''
    filename: str
    '''Filename string'''
    steps_string: str
    '''String documenting the steps given to :class:`pyopia.pipeline`
    This is put here for documentation purposes, and saving as metadata.
    '''
    cl: object
    '''classifier object from :class:`pyopia.classify.Classify`'''
    timestamp: datetime.datetime
    '''timestamp from e.g. :func:`pyopia.instrument.silcam.timestamp_from_filename()`'''
    imbw: float
    '''Segmented binary image identifying particles from water
    Obtained from e.g. :class:`pyopia.process.Segment`
    '''
    stats: pd.DataFrame
    '''stats DataFrame containing particle statistics of every particle
    Obtained from e.g. :class:`pyopia.process.CalculateStats`
    '''
    im_stack: float
    '''3-d array of reconstructed real hologram images
    Obtained from :class:`pyopia.instrument.holo.Reconstruct`
    '''
    imss: float
    '''Stack summary image used to locate possible particles
    Obtained from :class:`pyopia.instrument.holo.Focus`
    '''


def steps_to_string(steps):
    '''Deprecated. Convert pipeline steps dictionary to a human-readable string

    Args:
        steps (dict): pipeline steps dictionary

    Returns:
        str: human-readable string of the types and variables
    '''

    steps_str = '\n'
    for i, key in enumerate(steps.keys()):
        steps_str += (str(i + 1) + ') Step: ' + key
                      + '\n   Type: ' + str(type(steps[key]))
                      + '\n   Vars: ' + str(vars(steps[key]))
                      + '\n')
    return steps_str


class ReturnData():
    '''Pipeline compatible class that can be used for debugging
    if inserted as the last step in the steps dict.


    Pipeline input data:
    --------------------
    :class:`pyopia.pipeline.Data`

    containing any set of keys

    Returns:
    --------
    :class:`pyopia.pipeline.Data`

    Example use:
    ------------

    Config setup:

    .. code-block:: python

        [steps.returndata]
        pipeline_class = 'pyopia.classify.ReturnData'

    This will allow you to call pipeline.run() like this:

    .. code-block:: python

        data = pipeline.run(filename)

    where `data` will be the available data dictionary available at the point of calling this
    '''

    def __init__(self):
        pass

    def __call__(self, data):
        data['stats'] = data
        return data


def steps_from_xstats(xstats):
    '''Get the steps attribute from xarray version of the particle stats into a dictionary

    Parameters
    ----------
    xstats : xarray.DataSet
        xarray version of the particle stats dataframe, containing metadata

    Returns
    -------
    dict
        TOML-formatted dictionary of pipeline steps
    '''
    steps = toml.loads(xstats.__getattr__('steps'))
    return steps


def build_repr(toml_steps, step_name):
    '''Build a callable object from settings, which can be used to construct the pipeline steps dict

    Parameters
    ----------
    toml_steps : dict
        TOML-formatted steps
    step_name : str
        the key of the TOML-formatted steps which should be use to create a callable object

    Returns
    -------
    obj
        callable object, useable in a pipeline steps dict
    '''
    pipeline_class = toml_steps[step_name]['pipeline_class']
    classname = pipeline_class.split('.')[-1]
    modulename = pipeline_class.replace(classname, '')[:-1]

    keys = [k for k in toml_steps[step_name] if k != 'pipeline_class']

    arguments = dict()
    for k in keys:
        arguments[k] = toml_steps[step_name][k]

    m = methodcaller(classname, **arguments)
    callobj = m(sys.modules[modulename])
    return callobj


def build_steps(toml_steps):
    '''Build a steps dictionary, ready for pipeline use, from a TOML-formatted steps dict

    Parameters
    ----------
    toml_steps : dict
        TOML-formatted steps (usually loaded from a config.toml file)

    Returns
    -------
    dict
        steps dict that is useable by `pyopia.pipeline.Pipeline`
    '''
    step_names = list(toml_steps.keys())
    steps = dict()
    for step_name in step_names:
        steps[step_name] = build_repr(toml_steps, step_name)

    return steps


def get_load_function(instrument_module='imread'):
    if instrument_module == 'imread':
        return imread
    else:
        instrument = importlib.import_module(f'pyopia.instrument.{instrument_module}')
        return instrument.load_image
