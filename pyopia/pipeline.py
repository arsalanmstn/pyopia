'''
Module for managing the PyOpia processing pipeline

Refer to the :class:`Pipeline` class documentation for examples of how to process datasets and images
'''
from typing import TypedDict
import datetime
import pandas as pd
from operator import methodcaller
import sys
from pyopia.io import steps_from_xstats as steps_from_xstats # noqa: E(F401)
import logging
from glob import glob
import numpy as np

logger = logging.getLogger()


class Pipeline():
    '''The processing pipeline class

    Note
    ----
    The classes called in the Pipeline steps can be modified, and the names of the steps changed.
    New steps can be added or deleted as required.

    The classes called in the Pipeline steps need to take a TOML-formatted dictionary as input
    and return a dictionary of data as output. This common data dictionary: :class:`pyopia.pipeline.Data`
    is therefore passed between steps so that data or variables generated by each step can be passed along the pipeline.

    By default, the step names: `initial`, `classifier`, and `createbackground`
    are run when initialising `Pipeline`.
    The remaining steps will be run on Pipeline.run().
    You can add initial steps with the optional input `initial_steps`,
    which takes a list of strings of the step key names that should only be run on initialisation of the pipeline.
    i.e.: `processing_pipeline = pyopia.pipeline.Pipeline(toml_settings, initial_steps=['classifier', 'novel_initial_process'])`

    The step called 'classifier' must return a dict containing:
    :attr:`pyopia.pipeline.Data.cl` in order to run successfully.

    :func:`Pipeline.run()` takes a string as input.
    This string is put into :class:`pyopia.pipeline.Data`, available to the steps in the pipeline as `data['filename']`.
    This is intended for use in looping through several files during processing, so run can be
    called multiple times with different filenames.

    Examples
    --------

    Examples of setting up and running a pipeline
    can be found for SilCam `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/pipeline-holo.ipynb>`_,
    and holographic analysis `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/pipeline-holo.ipynb>`_.

    Example config files can be found for SilCam `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/config.toml>`_,
    and for holographic analysis `here <https://github.com/SINTEF/pyopia/blob/main/notebooks/config-holo.toml>`_.

    You can check the workflow used by reading the steps from the metadata in the
    output file using :func:`pyopia.io.steps_from_xstats`

    More examples and guides can be found on the `PyOIA By Example <https://pyopia.readthedocs.io/en/latest/examples.html>`_ page.
    '''

    def __init__(self, settings,
                 initial_steps=['initial', 'classifier', 'createbackground']):

        self.settings = settings
        self.stepnames = list(settings['steps'].keys())

        self.initial_steps = initial_steps
        logger.info('Initialising pipeline')
        self.data = Data()
        self.data['cl'] = None
        self.data['settings'] = settings

        # Flag used to control whether remaining pipeline steps should be skipped once it has been set to True
        self.data['skip_next_steps'] = False

        self.pass_general_settings()

        for stepname in self.stepnames:
            if not self.initial_steps.__contains__(stepname):
                continue
            self.run_step(stepname)

    def run(self, filename):
        '''Method for executing the processing pipeline.

        Parameters
        ----------
        filename : str
            file to be processed

        Returns
        -------
        stats : DataFrame
            particle statistics associated with 'filename'

        Note
        ----
        The returned stats from this function are single-image only and not appended
        if you loop through several filenames! It is recommended to use this step in the pipeline
        for properly appending data into NetCDF format when processing several files.

        .. code-block:: toml

            [steps.output]
            pipeline_class = 'pyopia.io.StatsDisc'
            output_datafile = 'proc/test'  # prefix path for output nc file
        '''

        self.data['filename'] = filename

        for stepname in self.stepnames:
            if self.initial_steps.__contains__(stepname):
                continue

            logger.info(f'Running pipeline step: {stepname}')
            self.run_step(stepname)

            # Check for signal from this step that we should skip remaining pipeline for this image
            if self.data['skip_next_steps']:
                logger.info('Skipping remaining steps of the pipeline and returning')

                # Reset skip flag
                self.data['skip_next_steps'] = False
                return

        return

    def run_step(self, stepname):
        '''Execute a pipeline step and update the pipeline data

        Parameters
        ----------
        stepname : str
            Name of the step defined in the settings
        '''
        if stepname == 'classifier':
            import pyopia.classify # noqa: E(F410)
            callobj = self.step_callobj(stepname)
            self.data['cl'] = callobj()
        else:
            callobj = self.step_callobj(stepname)
            self.data = callobj(self.data)

    def step_callobj(self, stepname):
        '''Generate a callable object for use in run_step()

        Parameters
        ----------
        stepname : str
            Name of the step defined in the settings

        Returns
        -------
        obj
            callable object for use in run_step()
        '''

        pipeline_class = self.settings['steps'][stepname]['pipeline_class']
        classname = pipeline_class.split('.')[-1]
        modulename = pipeline_class.replace(classname, '')[:-1]

        keys = [k for k in self.settings['steps'][stepname] if k != 'pipeline_class']

        arguments = dict()
        for k in keys:
            arguments[k] = self.settings['steps'][stepname][k]

        m = methodcaller(classname, **arguments)
        callobj = m(sys.modules[modulename])
        logger.debug(f'{classname} ready with: {arguments} and data: {self.data.keys()}')
        return callobj

    def pass_general_settings(self):
        self.data['raw_files'] = self.settings['general']['raw_files']

    def print_steps(self):
        '''Print the version number and steps dict (for log_level = DEBUG)
        '''

        # an eventual metadata parser could replace this below printing
        # and format into an appropriate standard
        logger.info('\n-- Pipeline configuration --\n')
        from pyopia import __version__ as pyopia_version
        logger.info(f'PyOpia version: {pyopia_version} + \n')
        logger.debug(steps_to_string(self.steps))
        logger.info('\n---------------------------------\n')


class Data(TypedDict):
    '''Data dictionary which is passed between :class:`pyopia.pipeline` steps.
    '''

    raw_files: str
    '''String used by glob to obtain file list of data to be processed
    This is exracted automatically from 'general.raw_files' in the toml config
    during pipeline initialisation.
    '''
    imraw: float
    '''Raw uncorrected image'''
    img: float
    '''Deprecatied. Replaced by imraw'''
    imc: float
    '''Deprecatied. Replaced by im_corrected'''
    im_corrected: float
    '''Single composite image of focussed particles ready for segmentation
    Obtained from e.g. :class:`pyopia.background.CorrectBackgroundAccurate`
    '''
    im_minimum: float
    '''A 2-d flattened RGB image representing the minmum intensity of all channels
    Obtained from e.g. :class:`pyopia.instrument.silcam.ImagePrep`'''
    bgstack: float
    '''List of images making up the background (either static or moving)
    Obtained from :class:`pyopia.background.CorrectBackgroundAccurate`
    '''
    imbg: float
    '''Background image that can be used to correct :attr:`pyopia.pipeline.Data.imraw`
    and calcaulte :attr:`pyopia.pipeline.Data.im_corrected`
    Obtained from :class:`pyopia.background.CorrectBackgroundAccurate`
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
    im_focussed: float
    '''Focussed holographic image'''
    imref: float
    '''Refereence background corrected image passed to silcam classifier'''
    im_masked: float
    '''Masked raw image with removed potentially noisy border region before further processsing
    Obtained from e.g. :class:`pyopia.instrument.common.RectangularImageMask`'''


def steps_to_string(steps):
    '''Deprecated. Convert pipeline steps dictionary to a human-readable string

    Parameters
    ----------
    steps : dict
        pipeline steps dictionary

    Returns
    -------
    steps_str : str
        human-readable string of the types and variables
    '''

    steps_str = '\n'
    for i, key in enumerate(steps.keys()):
        steps_str += (str(i + 1) + ') Step: ' + key
                      + '\n   Type: ' + str(type(steps[key]))
                      + '\n   Vars: ' + str(vars(steps[key]))
                      + '\n')
    return steps_str


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


class FilesToProcess:
    '''Build file list from glob pattern if specified.
    Create FilesToProcess.chunked_files is chunks specified
    File list from glob will be sorted.

    Parameters
    ----------
    glob_pattern : str, optional
        Glob pattern, by default None
    '''
    def __init__(self, glob_pattern=None):
        self.files = None
        self.background_files = []
        self.chunked_files = []
        if glob_pattern is not None:
            self.files = sorted(glob(glob_pattern))

    def from_filelist_file(self, path_to_filelist):
        '''
        Initialize explicit list of files to process from a text file.
        The text file should contain one path to an image per line, which should be processed in order.
        '''
        with open(path_to_filelist, 'r') as fh:
            self.files = list(fh.readlines())

    def to_filelist_file(self, path_to_filelist):
        '''Write file list to a txt file

        Parameters
        ----------
        path_to_filelist : str
            Path to txt file to write
        '''
        with open(path_to_filelist, 'w') as fh:
            [fh.writelines(L + '\n') for L in self.files]

    def prepare_chunking(self, num_chunks, average_window, bgshift_function):
        if num_chunks > len(self.files) // 2:
            raise RuntimeError('Number of chunks exceeds more than half the number of files to process. Use less chunks.')
        self.chunk_files(num_chunks)
        self.build_initial_background_files(average_window=average_window)
        self.insert_bg_files_into_chunks(bgshift_function=bgshift_function)

    def chunk_files(self, num_chunks: int):
        '''Chunk the file list and create FilesToProcess.chunked_files

        Parameters
        ----------
        num_chunks : int
            number of chunks to produce (must be at least 1)
        '''
        if num_chunks < 1:
            raise RuntimeError('You must have at least one chunk')
        chunk_length = int(np.ceil(len(self.files) / num_chunks))
        self.chunked_files = [self.files[i:i + chunk_length] for i in range(0, len(self.files), chunk_length)]

    def insert_bg_files_into_chunks(self, bgshift_function='pass'):
        average_window = len(self.background_files)
        for i, chunk in enumerate(self.chunked_files):
            if i > 0 and bgshift_function != 'pass':
                # If the bgshift_function is not pass then we need to find a new set of
                # background images for the start of next chunk. These will be the last
                # average_window number of files from the previous chunk.
                # If bgshift_function is 'pass', then we should use the same background files for all chunks
                # so there is no need to extend the list of background files here
                self.background_files.extend(self.chunked_files[i-1][-average_window:])
            # we have to loop backwards over bg_files because we are inserting into the top of the chunk
            chunk = [chunk.insert(0, bg_file) for bg_file in reversed(self.background_files[-average_window:])]

    def build_initial_background_files(self, average_window=0):
        '''Create a list of files to use for initializing the background in the first chunk

        Parameters
        ----------
        average_window : int, optional
            number of images to use in creating a background, by default 0
        '''
        self.background_files = []
        for f in self.files[0:average_window]:
            self.background_files.append(f)

    def __len__(self):
        return len(self.files)

    def __iter__(self):
        for filename in self.files:
            yield filename
