"""
The spm module provides basic functions for interfacing with matlab and spm to 
access spm tools.

these functions include 
    
    Realign: within-modality registration

    SliceTiming : correcting differences in image acquisition time between slices

    Coregister: between modality registration
    
    Normalize: non-linear warping to standard space

    Segment: bias correction, segmentation

"""
#from __future__ import with_statement

from nipype.interfaces.base import Bunch, CommandLine, Interface, setattr_on_read
from nipype.externals.pynifti import load
from nipype.interfaces.matlab import fltcols
import nipype.interfaces.matlab as matlab
from scipy.io import savemat
import numpy as np
import os
from nipype.utils import InTemporaryDirectory

mlab = matlab.Matlab()

class SpmInfo(object):
    @setattr_on_read
    def spm_path(self):
        try:
            InTemporaryDirectory()
            mlab.run_matlab_script("""
spm_path = spm('dir');
fid = fopen('spm_path.txt', 'wt');
fprintf(fid, '%s', spm_path);
fclose(fid);
""")
            spm_path = file('spm_path.txt', 'rt').read()
            return spm_path
        except:
            print 'Failed to return spm path'
            return None
       


spm_info = SpmInfo()


def make_job(jobtype, jobname, contents):
    return {'jobs':[{jobtype:[{jobname:contents}]}]}

def generate_job(prefix,contents):
    """ Recursive function to generate spm job specification as a string
    
    Arguments:
    - `prefix`:
    - `contents`:
    """
    jobstring = ''
    if type(contents) == type([]):
        for i,value in enumerate(contents):
            newprefix = "%s(%d)" % (prefix,i+1)
            jobstring += generate_job(newprefix,value)
        return jobstring
    if type(contents) == type({}):
        for key,value in contents.items():
            newprefix = "%s.%s" % (prefix,key)
            jobstring += generate_job(newprefix,value)
        return jobstring
    if type(contents) == type(np.empty(1)):
        #Assumes list of filenames embedded in a numpy array
        jobstring += "%s = {...\n"%(prefix)
        for item in contents:
            jobstring += '\'%s\';...\n'%(item)
        jobstring += '};\n'
        return jobstring
    if type(contents) == type(''):
        jobstring += "%s = '%s';\n" % (prefix,contents)
        return jobstring
    jobstring += "%s = %s;\n" % (prefix,str(contents))
    return jobstring

def make_mfile(jobtype, jobname, contents):
    """ generates a mfile to build job structure
    >>> import numpy as np
    >>> import nipype.interfaces.spm as spm
    >>> tmp = [{'estimate':{'files':np.array(['a.nii','b.nii']),'eoptions':{'interp':2},'roptions':{}}}]
    >>> spm.make_mfile('spatial','realign',tmp)
    """
    
    mfile = '% generated by nipype.interfaces.spm\n'
    mfile += "spm_defaults;\n\n"
    mfile += generate_job('jobs{1}.%s{1}.%s{1}' % (jobtype,jobname) ,contents[0])
    mfile += 'spm_jobman(\'run\',jobs);'
    return mfile

def make_mfile_old(jobtype, jobname, contents):
    """ generates a mfile to build job structure"""
    
    mfile = '% generated by nipype.interfaces.spm\n'
    mfile += "spm_defaults;\n\n"

    subfield = contents[0].keys()[0]
    #mfile += "jobs{1}.%s{1}.%s.data.scans = {...\n"%(jobtype,jobname)
    #for item in contents[0][subfield]['data']:
    #    mfile += '%s;...\n'%(item[0])
    #mfile += '};\n'

    for key, value in contents[0][subfield].items():
        if type(value) == type(np.empty(1)):
            mfile += "jobs{1}.%s{1}.%s{1}.%s.%s = {...\n"%(jobtype,
                                                           jobname,
                                                           subfield,
                                                           key)
            for item in contents[0][subfield][key]:
                 mfile += '\'%s\';...\n'%(item[0])
            mfile += '};\n'
                
        if type(value) == type({}):
            for skey,val in contents[0][subfield][key].items():
                mfile += 'jobs{1}.%s{1}.%s{1}.%s.%s.%s = %s;\n'%(jobtype,
                                                                 jobname,
                                                                 subfield,
                                                                 key,
                                                                 skey,
                                                                 val)
    #print mfile
    mfile += 'spm_jobman(\'run\',jobs);'
    return mfile

def run_jobdef(jobdef,jobname='',workdir='.'):
    # fix with specified path
    try:
        #InTemporaryDirectory()
        savemat('pyjobs.mat', jobdef)
        matlab_out=mlab.run_matlab_script("""
load pyjobs;
spm_jobman('run', jobs);
""",cwd=workdir)
        return matlab_out
    finally:
        print 'Failed to run jobdef'
        return None

def scans_for_fname(fname):
    img = load(fname)
    if len(img.get_shape()) == 3:
        scans = np.zeros((n_scans, 1), dtype=object)
        scans[0] = '%s,1'%(fname)
        return scans
    else:
        n_scans = img.get_shape()[3]
        scans = np.zeros((n_scans, 1), dtype=object)
        for sno in range(n_scans):
            scans[sno] = '%s,%d' % (fname, sno+1)
        return scans


def scans_for_fnames(fnames):
    n_sess = len(fnames)
    sess_scans = np.zeros((1,n_sess), dtype=object)
    for sess in range(n_sess):
        sess_scans[0,sess] = scans_for_fname(fnames[sess])
    return sess_scans


def fname_presuffix(fname, prefix='', suffix='', use_ext=True):
    pth, fname = os.path.split(fname)
    fname, ext = os.path.splitext(fname)
    if not use_ext:
        ext = ''
    return os.path.join(pth, prefix+fname+suffix+ext)


def fnames_presuffix(fnames, prefix='', suffix=''):
    f2 = []
    for fname in fnames:
        f2.append(fname_presuffix(fname, prefix, suffix))
    return f2


class Realign(CommandLine):
    """use spm_realign for estimating within modality
    rigid body alignment

    Parameters
    ----------
    inputs : mapping 
    key, value pairs that will update the Realign.inputs attributes
    see self.inputs_help() for a list of Realign.inputs attributes
    
    Attributes
    ----------
    inputs : Bunch
    a (dictionary-like) bunch of options that can be passed to 
    spm_realign via a job structure
    cmdline : string
    string used to call matlab/spm via CommandLine interface
    
    

    Options
    -------

    To see optional arguments
    Realign().inputs_help()


    Examples
    --------
    
    """
    
    @property
    def cmd(self):
        return 'spm_realign'
        
    def inputs_help(self):
        doc = """
            Optional Parameters
            -------------------
            (all default to None and are unset)

            infile : list
                list of filenames to realign
            write : bool
                if True updates headers and generates
                resliced files prepended with  'r'
                if False just updates header files
                (default == True, will reslice)
            quality : float
                0.1 = fastest, 1.0 = most precise
                (spm5 default = 0.9)
            fwhm : float
                full width half maximum gaussian kernel 
                used to smoth images before realigning
                (spm default = 5.0)
            separation : float
                separation in mm used to sample images
                (spm default = 4.0)
            register_to_mean: Bool
                rtm if True uses a two pass method
                realign -> calc mean -> realign all to mean
                (spm default = False)
            weight_img : file
                filename of weighting image
                if empty, no weighting 
                (spm default = None)
            wrap : list
                Check if interpolation should wrap in [x,y,z]
                (spm default [0,0,0])
            interp: float
                degree of b-spline used for interpolation
                (spm default = 2.0)
            write_which : list of len()==2
                if write is true, 
                [inputimgs, mean]
                [2,0] reslices all images, but not mean
                [2,1] reslices all images, and mean
                [1,0] reslices imgs 2:end, but not mean
                [0,1] doesnt reslice any but generates resliced mean
            write_interp: float
                degree of b-spline used for interpolation when
                writing resliced images
                (spm default = 4.0)
            write_wrap : list
                Check if interpolation should wrap in [x,y,z]
                (spm default [0,0,0])
            write_mask: bool
                if True, mask output image
                if False, do not mask
            flags : USE AT OWN RISK
                #eg:'flags':{'eoptions':{'suboption':value}}
                        
            """
        print doc

    def _populate_inputs(self):
        self.inputs = Bunch(infile=None,
                          write=True,
                          quality=None,
                          fwhm=None,
                          separation=None,
                          register_to_mean=None,
                          weight_img=None,
                          interp=None,
                          wrap=None,
                          write_which=None,
                          write_interp=None,
                          write_wrap=None,
                          write_mask=None,
                          flags=None)
        
    def _parseinputs(self):
        """validate spm realign options
        if set to None ignore
        """
        out_inputs = []
        inputs = {}
        einputs = {'eoptions':{},'roptions':{}}

        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v is not None ]
        for opt in inputs:
            if opt is 'flags':
                einputs.update(inputs[opt])
            if opt is 'infile':
                continue
            if opt is 'write':
                continue
            if opt is 'quality':
                einputs['eoptions'].update({'quality': float(inputs[opt])})
                continue
            if opt is 'fwhm':
                einputs['eoptions'].update({'fwhm': float(inputs[opt])})
                continue
            if opt is 'separation':
                einputs['eoptions'].update({'sep': float(inputs[opt])})
                continue
            if opt is 'register_to_mean':
                einputs['eoptions'].update({'rtm': 1})
                continue
            if opt is 'weight_img':
                einputs['eoptions'].update({'weight': inputs[opt]})
                continue
            if opt is 'interp':
                einputs['eoptions'].update({'interp': float(inputs[opt])})
                continue
            if opt is 'wrap':
                if not len(inputs[opt]) == 3:
                    raise ValueError('wrap must have 3 elements')
                einputs['eoptions'].update({'wrap': inputs[opt]})
                continue
            if opt is 'write_which':
                if not len(inputs[opt]) == 2:
                    raise ValueError('write_which must have 2 elements')
                einputs['roptions'].update({'which': inputs[opt]})
                continue
            if opt is 'write_interp':
                einputs['roptions'].update({'interp': inputs[opt]})
                continue
            if opt is 'write_wrap':
                if not len(inputs[opt]) == 3:
                    raise ValueError('write_wrap must have 3 elements')
                einputs['roptions'].update({'wrap': inputs[opt]})
                continue
            if opt is 'write_mask':
                einputs['roptions'].update({'mask': int(inputs[opt])})
                continue
                
            print 'option %s not supported'%(opt)
        return einputs

    def run(self, mfile=True):
        
        job = self._compile_command(mfile)

        if mfile:
            out, cmdline = mlab.run_matlab_script(job, 
                                                  script_name='pyscript_spmrealign')
        else:
            out = run_jobdef(job)
            cmdline = ''
            
        outputs = Bunch(outfiles = fnames_prefix(self.inputs.infile,'r'))
        output = Bunch(returncode=returncode,
                       stdout=out,
                       stderr=err,
                       outputs=outputs,
                       interface=self.copy())
        return output
        
        
    def _compile_command(self,mfile=True):
        """validates spm options and generates job structure
        if mfile is True uses matlab .m file
        else generates a job structure and saves in .mat
        """
        if self.inputs.write:
            jobtype = 'estwrite'
        else:
            jobtype = 'estimate'
        valid_inputs = self._parseinputs()
        if type(self.inputs.infile) == type([]):
            sess_scans = scans_for_fnames(self.inputs.infile)
        else:
            sess_scans = scans_for_fname(self.inputs.infile)

        
        # create job structure form valid options and data
        tmp = [{'%s'%(jobtype):{'data':sess_scans,
                                'eoptions':valid_inputs['eoptions'],
                                'roptions':valid_inputs['roptions']
                                }}]
        if mfile:
            return make_mfile('spatial','realign',tmp)
        else:
            return make_job('spatial','realign',tmp)


class Coregister(CommandLine):
    """use spm_coreg for estimating cross-modality
    rigid body alignment

    Parameters
    ----------
    inputs : mapping 
    key, value pairs that will update the Coregister.inputs attributes
    see self.inputs_help() for a list of Coregister.inputs attributes
    
    Attributes
    ----------
    inputs : Bunch
    a (dictionary-like) bunch of options that can be passed to 
    spm_coreg via a job structure
    cmdline : string
    string used to call matlab/spm via CommandLine interface
    
    

    Options
    -------

    To see optional arguments
    Coregister().inputs_help()


    Examples
    --------
    
    """
    
    @property
    def cmd(self):
        return 'spm_coreg'
        
    def inputs_help(self):
        doc = """
            Mandatory Parameters
            -------------------- 
            target : string
                filename of nifti image to coregister to
            source : string
                filename of nifti image to coregister to the reference

            Optional Parameters
            -------------------
            (all default to None and are unset)

            infile : list
                list of filenames to apply the estimated rigid body
                transform from source to target 
            write : bool
                if True updates headers and generates resliced files
                prepended with  'r' if False just updates header files
                (default == True, will reslice) 
            cost_function: string
                maximise   or   minimise   some   objective
                function. For inter-modal    registration,    use
                Mutual   Information (mi), Normalised Mutual
                Information (nmi), or  Entropy  Correlation
                Coefficient (ecc). For within modality, you could also
                use Normalised Cross Correlation (ncc).
                (spm default = mi)
            separation : float
                separation in mm used to sample images
                (spm default = 4.0)
            tolerance: list of 12 floats
                The   accuracy  for  each  parameter.  Iterations
                stop  when differences  between  successive  estimates
                are less than the required tolerance for each of the
                12 parameters.
            fwhm : float
                full width half maximum gaussian kernel 
                used to smoth images before coregistering
                (spm default = 5.0)
            write_interp: int
                degree of b-spline used for interpolation when
                writing resliced images (0 - Nearest neighbor, 1 - 
                Trilinear, 2-7 - degree of b-spline)
                (spm default = 0 - Nearest Neighbor)
            write_wrap : list
                Check if interpolation should wrap in [x,y,z]
                (spm default [0,0,0])
            write_mask: bool
                if True, mask output image
                if False, do not mask
                (spm default = False)
            flags : USE AT OWN RISK
                #eg:'flags':{'eoptions':{'suboption':value}}
                        
            """
        print doc

    def _populate_inputs(self):
        self.inputs = Bunch(target=None,
                            source=None,
                            infile=None,
                            write=True,
                            cost_function=None,
                            separation=None,
                            tolerance=None,
                            fwhm=None,
                            write_interp=None,
                            write_wrap=None,
                            write_mask=None,
                            flags=None)
        
    def _parseinputs(self):
        """validate spm coregister options
        if set to None ignore
        """
        out_inputs = []
        inputs = {}
        einputs = {'eoptions':{},'roptions':{}}

        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v is not None ]
        for opt in inputs:
            if opt is 'target':
                continue
            if opt is 'source':
                continue
            if opt is 'infile':
                continue
            if opt is 'write':
                continue
            if opt is 'cost_function':
                einputs['eoptions'].update({'cost_fun': inputs[opt]})
                continue
            if opt is 'separation':
                einputs['eoptions'].update({'sep': float(inputs[opt])})
                continue
            if opt is 'tolerance':
                einputs['eoptions'].update({'tol': inputs[opt]})
                continue
            if opt is 'fwhm':
                einputs['eoptions'].update({'fwhm': float(inputs[opt])})
                continue
            if opt is 'write_interp':
                einputs['roptions'].update({'interp': inputs[opt]})
                continue
            if opt is 'write_wrap':
                if not len(inputs[opt]) == 3:
                    raise ValueError('write_wrap must have 3 elements')
                einputs['roptions'].update({'wrap': inputs[opt]})
                continue
            if opt is 'write_mask':
                einputs['roptions'].update({'mask': int(inputs[opt])})
                continue
            if opt is 'flags':
                einputs.update(inputs[opt])
                continue
            print 'option %s not supported'%(opt)
        return einputs

    def run(self, mfile=True):
        
        job = self._compile_command(mfile)

        if mfile:
            out, cmdline = mlab.run_matlab_script(job, 
                                                  script_name='pyscript_spmcoreg')
        else:
            out = run_jobdef(job)
            cmdline = ''
            
        outputs = Bunch(outfiles = fnames_prefix(self.inputs.infile,'r'))
        output = Bunch(returncode=returncode,
                       stdout=out,
                       stderr=err,
                       outputs=outputs,
                       interface=self.copy())
        return output
        
        
    def _compile_command(self,mfile=True):
        """validates spm options and generates job structure
        if mfile is True uses matlab .m file
        else generates a job structure and saves in .mat
        """
        if self.inputs.write:
            jobtype = 'estwrite'
        else:
            jobtype = 'estimate'
        valid_inputs = self._parseinputs()
        if type(self.inputs.infile) == type([]):
            sess_scans = scans_for_fnames(self.inputs.infile)
        else:
            sess_scans = scans_for_fname(self.inputs.infile)

        
        # create job structure form valid options and data
        tmp = [{'%s'%(jobtype):{'ref':self.inputs.target,
                                'source':self.inputs.source,
                                'other':sess_scans,
                                'eoptions':valid_inputs['eoptions'],
                                'roptions':valid_inputs['roptions']
                                }}]
        if mfile:
            return make_mfile('spatial','coreg',tmp)
        else:
            return make_job('spatial','coreg',tmp)

        
class Normalize(CommandLine):
    """use spm_normalise for warping an image to a template

    Parameters
    ----------
    inputs : mapping 
    key, value pairs that will update the Normalize.inputs attributes
    see self.inputs_help() for a list of Normalize.inputs attributes
    
    Attributes
    ----------
    inputs : Bunch
    a (dictionary-like) bunch of options that can be passed to 
    spm_normalise via a job structure
    cmdline : string
    string used to call matlab/spm via CommandLine interface
    
    

    Options
    -------

    To see optional arguments
    Normalize().inputs_help()


    Examples
    --------
    
    """
    
    @property
    def cmd(self):
        return 'spm_normalise'

    def inputs_help(self):
        doc = """
            Mandatory Parameters
            --------------------
            template : string
                filename of nifti image to normalize to
            source : string
                filename of nifti image to normalize

            Optional Parameters
            -------------------
            (all default to None and are unset)

            infile : list
                list of filenames to apply the estimated normalization
            write : bool
                if True updates headers and generates resliced files
                prepended with  'r' if False just updates header files
                (default == True, will reslice)
            source_weight : string
                name of weighting image for source
            template_weight : string
                name of weighting image for template
            source_image_smoothing: float
            template_image_smoothing: float
            affine_regularization_type: string
                ICBM space template (mni), average sized template
                (size), no regularization (none)
            DCT_period_cutoff: int
                Cutoff  of  DCT  bases. Only DCT bases of periods
                longer than cutoff  are  used to describe the warps. 
                spm default = 25
            nonlinear_iterations: int
                Number of iterations of nonlinear warping
                spm default = 16
            nonlinear_regularization: float
                min = 0  max = 1
                spm default = 1
            write_preserve: int
                Preserve  Concentrations (0): Spatially normalised images
                are not "modulated".  The  warped  images preserve the
                intensities of the original images. Preserve  Total (1):
                Spatially normalised images are "modulated" in  order
                to  preserve  the  total  amount  of signal in the
                images.   Areas   that   are   expanded  during
                warping  are correspondingly reduced in intensity.
                spm default = 0 
            write_bounding_box: 6-element list
            write_voxel_sizes: 3-element list
            write_interp: int
                degree of b-spline used for interpolation when
                writing resliced images (0 - Nearest neighbor, 1 - 
                Trilinear, 2-7 - degree of b-spline)
                (spm default = 0 - Nearest Neighbor)
            write_wrap : list
                Check if interpolation should wrap in [x,y,z]
                (spm default [0,0,0])
            flags : USE AT OWN RISK
                #eg:'flags':{'eoptions':{'suboption':value}}
            """
        print doc

    def _populate_inputs(self):
        self.inputs = Bunch(template=None,
                            source=None,
                            infile=None,
                            write=True,
                            source_weight=None,
                            template_weight=None,
                            source_image_smoothing=None,
                            template_image_smoothing=None,
                            affine_regularization_type=None,
                            DCT_period_cutoff=None,
                            nonlinear_iterations=None,
                            nonlinear_regularization=None,
                            write_preserve=None,
                            write_bounding_box=None,
                            write_voxel_sizes=None,
                            write_interp=None,
                            write_wrap=None,
                            flags=None)
        
    def _parseinputs(self):
        """validate spm normalize options
        if set to None ignore
        """
        out_inputs = []
        inputs = {}
        einputs = {'subj':{},'eoptions':{},'roptions':{}}

        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v is not None ]
        for opt in inputs:
            if opt is 'template':
                einputs['eoptions'].update({'template': inputs[opt]})
                continue
            if opt is 'source':
                einputs['subj'].update({'source': inputs[opt]})
                continue
            if opt is 'infile':
                continue
            if opt is 'write':
                continue
            if opt is 'source_weight':
                einputs['subj'].update({'wtsrc': inputs[opt]})
                continue
            if opt is 'template_weight':
                einputs['eoptions'].update({'weight': inputs[opt]})
                continue
            if opt is 'source_image_smoothing':
                einputs['eoptions'].update({'smosrc': float(inputs[opt])})
                continue
            if opt is 'template_image_smoothing':
                einputs['eoptions'].update({'smoref': float(inputs[opt])})
                continue
            if opt is 'affine_regularization_type':
                einputs['eoptions'].update({'regtype': inputs[opt]})
                continue
            if opt is 'DCT_period_cutoff':
                einputs['eoptions'].update({'cutoff': inputs[opt]})
                continue
            if opt is 'nonlinear_iterations':
                einputs['eoptions'].update({'nits': inputs[opt]})
                continue
            if opt is 'nonlinear_regularization':
                einputs['eoptions'].update({'reg': float(inputs[opt])})
                continue
            if opt is 'write_preserve':
                einputs['roptions'].update({'preserve': inputs[opt]})
                continue
            if opt is 'write_bounding_box':
                einputs['roptions'].update({'bb': inputs[opt]})
                continue
            if opt is 'write_voxel_sizes':
                einputs['roptions'].update({'vox': inputs[opt]})
                continue
            if opt is 'write_interp':
                einputs['roptions'].update({'interp': inputs[opt]})
                continue
            if opt is 'write_wrap':
                if not len(inputs[opt]) == 3:
                    raise ValueError('write_wrap must have 3 elements')
                einputs['roptions'].update({'wrap': inputs[opt]})
                continue
            if opt is 'flags':
                einputs.update(inputs[opt])
                continue
            print 'option %s not supported'%(opt)
        return einputs

    def run(self, mfile=True):
        
        job = self._compile_command(mfile)

        if mfile:
            out, cmdline = mlab.run_matlab_script(job, 
                                                  script_name='pyscript_spmnormalize')
        else:
            out = run_jobdef(job)
            cmdline = ''
            
        outputs = Bunch(outfiles = fnames_prefix(self.inputs.infile,'r'))
        output = Bunch(returncode=returncode,
                       stdout=out,
                       stderr=err,
                       outputs=outputs,
                       interface=self.copy())
        return output
        
        
    def _compile_command(self,mfile=True):
        """validates spm options and generates job structure
        if mfile is True uses matlab .m file
        else generates a job structure and saves in .mat
        """
        if self.inputs.write:
            jobtype = 'estwrite'
        else:
            jobtype = 'est'
        valid_inputs = self._parseinputs()
        if type(self.inputs.infile) == type([]):
            sess_scans = scans_for_fnames(self.inputs.infile)
        else:
            sess_scans = scans_for_fname(self.inputs.infile)

        valid_inputs['subj']['resample'] = sess_scans
        
        # create job structure form valid options and data
        tmp = [{'%s'%(jobtype):{'subj':valid_inputs['subj'],
                                'eoptions':valid_inputs['eoptions'],
                                'roptions':valid_inputs['roptions']
                                }}]
        if mfile:
            return make_mfile('spatial','normalise',tmp)
        else:
            return make_job('spatial','normalise',tmp)

class Smooth(CommandLine):
    """use spm_smooth for 3D Gaussian smoothing of image volumes.

    Parameters
    ----------
    inputs : mapping 
    key, value pairs that will update the Smooth.inputs attributes
    see self.inputs_help() for a list of Smooth.inputs attributes
    
    Attributes
    ----------
    inputs : Bunch
    a (dictionary-like) bunch of options that can be passed to 
    spm_smooth via a job structure
    cmdline : string
    string used to call matlab/spm via CommandLine interface
    
    

    Options
    -------

    To see optional arguments
    Smooth().inputs_help()


    Examples
    --------
    
    """
    
    @property
    def cmd(self):
        return 'spm_smooth'

    def inputs_help(self):
        doc = """
            Mandatory Parameters
            --------------------
            infile : list
                list of filenames to apply smoothing

            Optional Parameters
            -------------------
            (all default to None and are unset)

            fwhm : 3-list
                list of fwhm for each dimension
            data_type : int
                spm default = 0
            flags : USE AT OWN RISK
                #eg:'flags':{'eoptions':{'suboption':value}}
            """
        print doc

    def _populate_inputs(self):
        self.inputs = Bunch(infile=None,
                            fwhm=None,
                            flags=None)
        
    def _parseinputs(self):
        """validate spm normalize options
        if set to None ignore
        """
        out_inputs = []
        inputs = {}
        einputs = {'fwhm':[],'dtype':0}

        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v is not None ]
        for opt in inputs:
            if opt is 'infile':
                continue
            if opt is 'fwhm':
                einputs['fwhm'] = inputs[opt]
                continue
            if opt is 'data_type':
                einputs['dtype'] = inputs[opt]
                continue
            if opt is 'flags':
                einputs.update(inputs[opt])
                continue
            print 'option %s not supported'%(opt)
        return einputs

    def run(self, mfile=True):
        
        job = self._compile_command(mfile)

        if mfile:
            out, cmdline = mlab.run_matlab_script(job, 
                                                  script_name='pyscript_spmnormalize')
        else:
            out = run_jobdef(job)
            cmdline = ''
            
        outputs = Bunch(outfiles = fnames_prefix(self.inputs.infile,'r'))
        output = Bunch(returncode=returncode,
                       stdout=out,
                       stderr=err,
                       outputs=outputs,
                       interface=self.copy())
        return output
        
        
    def _compile_command(self,mfile=True):
        """validates spm options and generates job structure
        if mfile is True uses matlab .m file
        else generates a job structure and saves in .mat
        """
        valid_inputs = self._parseinputs()
        if type(self.inputs.infile) == type([]):
            sess_scans = scans_for_fnames(self.inputs.infile)
        else:
            sess_scans = scans_for_fname(self.inputs.infile)

        # create job structure form valid options and data
        tmp = [{'data':sess_scans,
                'fwhm':valid_inputs['fwhm'],
                }]
        if mfile:
            return make_mfile('spatial','smooth',tmp)
        else:
            return make_job('spatial','smooth',tmp)

        
