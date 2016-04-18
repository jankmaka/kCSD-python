"""
This script is used to generate Current Source Density Estimates, 
using the kCSD method Jan et.al (2012) for 2D case.

These scripts are based on Grzegorz Parka's, 
Google Summer of Code 2014, INFC/pykCSD  

This was written by :
Chaitanya Chintaluri, 
Laboratory of Neuroinformatics,
Nencki Institute of Exprimental Biology, Warsaw.
"""
import numpy as np
from scipy import integrate
from scipy.spatial import distance
from numpy.linalg import LinAlgError

from CSD import CSD
import utility_functions as utils
import basis_functions as basis

class KCSD2D(CSD):
    """KCSD2D - The 2D variant for the Kernel Current Source Density method.

    This estimates the Current Source Density, for a given configuration of 
    electrod positions and recorded potentials, in the case of 2D recording
    electrodes. The method implented here is based on the original paper
    by Jan Potworowski et.al. 2012.
    """
    def __init__(self, ele_pos, pots, **kwargs):
        """Initialize KCSD2D Class.

        Parameters
        ----------
        ele_pos : numpy array
            positions of electrodes
        pots : numpy array
            potentials measured by electrodes
        **kwargs
            configuration parameters, that may contain the following keys:
            src_type : str
                basis function type ('gauss', 'step', 'gauss_lim')
                Defaults to 'gauss'
            sigma : float
                space conductance of the medium
                Defaults to 1.
            n_src_init : int
                requested number of sources
                Defaults to 1000
            R_init : float
                demanded thickness of the basis element
                Defaults to 0.23
            h : float
                thickness of analyzed tissue slice
                Defaults to 1.
            xmin, xmax, ymin, ymax : floats
                boundaries for CSD estimation space
                Defaults to min(ele_pos(x)), and max(ele_pos(x))
                Defaults to min(ele_pos(y)), and max(ele_pos(y))
            ext_x, ext_y : float
                length of space extension: x_min-ext_x ... x_max+ext_x
                length of space extension: y_min-ext_y ... y_max+ext_y 
                Defaults to 0.
            gdx, gdy : float
                space increments in the estimation space
                Defaults to 0.01(xmax-xmin)
                Defaults to 0.01(ymax-ymin)
            lambd : float
                regularization parameter for ridge regression
                Defaults to 0.

        Returns
        -------
        None
        """
        super(KCSD2D, self).__init__(ele_pos, pots)
        self.parameters(**kwargs)
        self.estimate_at() 
        self.place_basis() 
        self.method()
        return

    def parameters(self, **kwargs):
        """Defining the default values of the method passed as kwargs
        Parameters
        ----------
        **kwargs
            Same as those passed to initialize the Class

        Returns
        -------
        None
        """
        self.src_type = kwargs.get('src_type', 'gauss')
        self.sigma = kwargs.get('sigma', 1.0)
        self.h = kwargs.get('h', 1.0)
        self.n_src_init = kwargs.get('n_src_init', 1000)
        self.ext_x = kwargs.get('ext_x', 0.0)
        self.ext_y = kwargs.get('ext_y', 0.0)
        self.lambd = kwargs.get('lambd', 0.0)
        self.R_init = kwargs.get('R_init', 0.23)
        #If no estimate plane given, take electrode plane as estimate plane
        self.xmin = kwargs.get('xmin', np.min(self.ele_pos[:, 0]))
        self.xmax = kwargs.get('xmax', np.max(self.ele_pos[:, 0]))
        self.ymin = kwargs.get('ymin', np.min(self.ele_pos[:, 1]))
        self.ymax = kwargs.get('ymax', np.max(self.ele_pos[:, 1]))
        #Space increment size in estimation
        self.gdx = kwargs.get('gdx', 0.01*(self.xmax - self.xmin)) 
        self.gdy = kwargs.get('gdy', 0.01*(self.ymax - self.ymin))
        return
        
    def estimate_at(self):
        """Defines locations where the estimation is wanted
        Defines:         
        self.n_estm = self.estm_x.size
        self.ngx, self.ngy = self.estm_x.shape
        self.estm_x, self.estm_y : Locations at which CSD is requested.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        #Number of points where estimation is to be made.
        nx = (self.xmax - self.xmin)/self.gdx
        ny = (self.ymax - self.ymin)/self.gdy
        #Making a mesh of points where estimation is to be made.
        self.estm_x, self.estm_y = np.mgrid[self.xmin:self.xmax:np.complex(0,nx), 
                                            self.ymin:self.ymax:np.complex(0,ny)]
        self.n_estm = self.estm_x.size
        self.ngx, self.ngy = self.estm_x.shape
        return

    def place_basis(self):
        """Places basis sources of the defined type.
        Checks if a given source_type is defined, if so then defines it
        self.basis, This function gives locations of the basis sources, 
        Defines
        source_type : basis_fuctions.basis_2D.keys()
        self.R based on R_init
        self.dist_max as maximum distance between electrode and basis
        self.nsx, self.nsy = self.src_x.shape
        self.src_x, self.src_y : Locations at which basis sources are placed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        #If Valid basis source type passed?
        source_type = self.src_type
        if source_type not in basis.basis_2D.keys():
            raise Exception('Invalid source_type for basis! available are:', 
                            basis.basis_2D.keys())
        else:
            self.basis = basis.basis_2D.get(source_type)
        #Mesh where the source basis are placed is at self.src_x 
        (self.src_x, self.src_y, self.R) = utils.distribute_srcs_2D(self.estm_x,
                                                                    self.estm_y,
                                                                    self.n_src_init,
                                                                    self.ext_x, 
                                                                    self.ext_y,
                                                                    self.R_init ) 
        #Total diagonal distance of the area covered by the basis sources
        Lx = np.max(self.src_x) - np.min(self.src_x) + self.R
        Ly = np.max(self.src_y) - np.min(self.src_y) + self.R
        self.dist_max = (Lx**2 + Ly**2)**0.5
        self.n_src = self.src_x.size
        self.nsx, self.nsy = self.src_x.shape
        return        
        
    def method(self):
        """Actual sequence of methods called for KCSD
        Defines:
        self.k_pot and self.k_interp_cross matrices

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.create_lookup()                                #Look up table 
        self.update_b_pot()                                 #update kernel
        self.update_b_src()                                 #update crskernel
        self.update_b_interp_pot()                          #update pot interp
        return

    def values(self, estimate='CSD'):
        """Computes the values of the quantity of interest

        Parameters
        ----------
        estimate : 'CSD' or 'POT'
            What quantity is to be estimated
            Defaults to 'CSD'

        Returns
        -------
        estimated quantity of shape (ngx, ngy, nt)
        """
        if estimate == 'CSD':       
            estimation_table = self.k_interp_cross 
        elif estimate == 'POT':
            estimation_table = self.k_interp_pot
        else:
            print 'Invalid quantity to be measured, pass either CSD or POT'
        k_inv = np.linalg.inv(self.k_pot + self.lambd *
                              np.identity(self.k_pot.shape[0]))
        estimation = np.zeros((self.n_estm, self.n_time))
        for t in xrange(self.n_time):
            beta = np.dot(k_inv, self.pots[:, t])
            for i in xrange(self.n_ele):
                estimation[:, t] += estimation_table[:, i] * beta[i]  
                #C*(x) Eq 18
        estimation = estimation.reshape(self.ngx, self.ngy, self.n_time)
        return estimation

    def create_lookup(self, dist_table_density=100):
        """Creates a table for easy potential estimation from CSD.
        Updates and Returns the potentials due to a given basis 
        source like a lookup table whose 
        shape=(dist_table_density,)--> set in KCSD2D_Helpers.py

        Parameters
        ----------
        dist_table_density : int
            number of distance values at which potentials are computed.
            Default 100

        Returns
        -------
        None
        """
        dt_len = dist_table_density
        xs = utils.sparse_dist_table(self.R, #Find pots at sparse points
                                     self.dist_max, 
                                     dt_len)
        dist_table = np.zeros(len(xs))
        for i, x in enumerate(xs):
            pos = (x/dt_len) * self.dist_max
            dist_table[i] = self.forward_model(pos, self.R,
                                               self.h, self.sigma,
                                               self.basis)
        self.dist_table = utils.interpolate_dist_table(xs, dist_table, dt_len) 
        return

    def update_b_pot(self):
        """Updates the b_pot  - array is (#_basis_sources, #_electrodes)
        Updates the  k_pot - array is (#_electrodes, #_electrodes) K(x,x') 
        Eq9,Jan2012
        Calculates b_pot - matrix containing the values of all
        the potential basis functions in all the electrode positions
        (essential for calculating the cross_matrix).

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        src = np.array((self.src_x.ravel(), self.src_y.ravel()))
        dists = distance.cdist(src.T, self.ele_pos, 'euclidean')
        self.b_pot = self.generated_potential(dists)
        self.k_pot = np.dot(self.b_pot.T, self.b_pot) #K(x,x') Eq9,Jan2012
        self.k_pot /= self.n_src
        return
    
    def update_b_src(self):
        """Updates the b_src in the shape of (#_est_pts, #_basis_sources)
        Updates the k_interp_cross - K_t(x,y) Eq17
        Calculate b_src - matrix containing containing the values of
        all the source basis functions in all the points at which we want to
        calculate the solution (essential for calculating the cross_matrix)

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.b_src = np.zeros((self.ngx, self.ngy, self.n_src))
        for i in xrange(self.n_src):
            # getting the coordinates of the i-th source
            (i_x, i_y) = np.unravel_index(i, (self.nsx, self.nsy), order='C')
            x_src = self.src_x[i_x, i_y]
            y_src = self.src_y[i_x, i_y]
            self.b_src[:, :, i] = self.basis(self.estm_x, 
                                             self.estm_y,
                                             [x_src, y_src],
                                             self.R)
        self.b_src = self.b_src.reshape(self.n_estm, self.n_src)
        self.k_interp_cross = np.dot(self.b_src, self.b_pot) #K_t(x,y) Eq17
        self.k_interp_cross /= self.n_src
        return
        
    def update_b_interp_pot(self):
        """Compute the matrix of potentials generated by every source
        basis function at every position in the interpolated space.
        Updates b_interp_pot
        Updates k_interp_pot

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        src_loc = np.array((self.src_x.ravel(), self.src_y.ravel()))
        est_loc = np.array((self.estm_x.ravel(), self.estm_y.ravel()))
        dists = distance.cdist(src_loc.T, est_loc.T,  'euclidean')
        self.b_interp_pot = self.generated_potential(dists).T
        self.k_interp_pot = np.dot(self.b_interp_pot, self.b_pot)
        self.k_interp_pot /= self.n_src
        return

    def generated_potential(self, dist):
        """Fetches values from the look up table - FWD model

        Parameters
        ----------
        dist : float
            distance at which we want to obtain the potential value

        Returns
        -------
        pot : float
            value of potential at specified distance from the source
        """
        dt_len = len(self.dist_table)
        indices = np.uint16(np.round(dt_len * dist/self.dist_max))
        ind = np.maximum(0, np.minimum(indices, dt_len-1))
        pot = self.dist_table[ind]
        return pot


    def forward_model(self, x, R, h, sigma, src_type):
        """FWD model functions
        Evaluates potential at point (x,0) by a basis source located at (0,0)
        Eq 22 kCSD by Jan,2012

        Parameters
        ----------
        x : float
        R : float
        h : float
        sigma : float
        src_type : basis_2D.key

        Returns
        -------
        pot : float
            value of potential at specified distance from the source
        """
        pot, err = integrate.dblquad(self.int_pot_2D, 
                                     -R, R, 
                                     lambda x: -R, 
                                     lambda x: R, 
                                     args=(x, R, h, src_type))
        pot *= 1./(2.0*np.pi*sigma)  #Potential basis functions bi_x_y
        return pot

    def int_pot_2D(self, xp, yp, x, R, h, basis_func):
        """FWD model function.
        Returns contribution of a point xp,yp, belonging to a basis source
        support centered at (0,0) to the potential measured at (x,0),
        integrated over xp,yp gives the potential generated by a
        basis source element centered at (0,0) at point (x,0)

        Parameters
        ----------
        xp, yp : floats or np.arrays
            point or set of points where function should be calculated
        x :  float
            position at which potential is being measured
        R : float
            The size of the basis function
        h : float
            thickness of slice
        basis_func : method
            Fuction of the basis source

        Returns
        -------
        pot : float
        """
        y = ((x-xp)**2 + yp**2)**(0.5)
        if y < 0.00001:
            y = 0.00001
        pot = np.arcsinh(h/y)
        pot *= basis_func(xp, yp, [0, 0], R) #[0, 0] is origin here
        return pot
    
    def update_R(self, R):
        """Used in Cross validation

        Parameters
        ----------
        R : float

        Returns
        -------
        None
        """
        self.R = R
        Lx = np.max(self.src_x) - np.min(self.src_x) + self.R
        Ly = np.max(self.src_y) - np.min(self.src_y) + self.R
        self.dist_max = (Lx**2 + Ly**2)**0.5
        self.method()
        return

    def update_lambda(self, lambd):
        """Used in Cross validation

        Parameters
        ----------
        lambd : float

        Returns
        -------
        None
        """
        self.lambd = lambd
        return

    def cross_validate(self, lambdas=None, Rs=None): 
        """Method defines the cross validation.
        By default only cross_validates over lambda, 
        When no argument is passed, it takes
        lambdas = np.logspace(-2,-25,25,base=10.)
        and Rs = np.array(self.R).flatten()
        otherwise pass necessary numpy arrays

        Parameters
        ----------
        lambdas : numpy array
        Rs : numpy array

        Returns
        -------
        R : post cross validation
        Lambda : post cross validation
        """
        if not np.any(lambdas):                       #when None
            lambdas = np.logspace(-2,-25,25,base=10.) #Default multiple lambda
        if not np.any(Rs):                            #when None
            Rs = np.array((self.R)).flatten()         #Default over one R value
        errs = np.zeros((Rs.size, lambdas.size))
        index_generator = []                          
        for ii in range(self.n_ele):
            idx_test = [ii]                           
            idx_train = range(self.n_ele)
            idx_train.remove(ii)                      #Leave one out
            index_generator.append((idx_train, idx_test))
        for R_idx,R in enumerate(Rs):                 #Iterate over R
            self.update_R(R)
            print 'Cross validating R (all lambda) :', R
            for lambd_idx,lambd in enumerate(lambdas): #Iterate over lambdas
                errs[R_idx, lambd_idx] = self.compute_cverror(lambd, 
                                                              index_generator)
        err_idx = np.where(errs==np.min(errs))         #Index of the least error
        cv_R = Rs[err_idx[0]][0]      #First occurance of the least error's
        cv_lambda = lambdas[err_idx[1]][0]
        self.cv_error = np.min(errs)  #otherwise is None
        self.update_R(cv_R)           #Update solver
        self.update_lambda(cv_lambda)
        print 'R, lambda :', cv_R, cv_lambda
        return cv_R, cv_lambda

    def compute_cverror(self, lambd, index_generator):
        """Useful for Cross validation error calculations

        Parameters
        ----------
        lambd : float
        index_generator : list

        Returns
        -------
        err : float
            the sum of the error computed.
        """
        err = 0
        for idx_train, idx_test in index_generator:
            B_train = self.k_pot[np.ix_(idx_train, idx_train)]
            V_train = self.pots[idx_train]
            V_test = self.pots[idx_test]
            I_matrix = np.identity(len(idx_train))
            B_new = np.matrix(B_train) + (lambd*I_matrix)
            try:
                beta_new = np.dot(np.matrix(B_new).I, np.matrix(V_train))
                B_test = self.k_pot[np.ix_(idx_test, idx_train)]
                V_est = np.zeros((len(idx_test), self.pots.shape[1]))
                for ii in range(len(idx_train)):
                    for tt in range(self.pots.shape[1]):
                        V_est[:, tt] += beta_new[ii, tt] * B_test[:, ii]
                err += np.linalg.norm(V_est-V_test)
            except LinAlgError:
                print 'Encoutered Singular Matrix Error: try changing ele_pos'
                err = 10000. #singluar matrix errors!
        return err

if __name__ == '__main__':
    #Sample data, do not take this seriously
    ele_pos = np.array([[-0.2, -0.2],[0, 0], [0, 1], [1, 0], [1,1], [0.5, 0.5],
                        [1.2, 1.2]])
    pots = np.array([[-1], [-1], [-1], [0], [0], [1], [-1.5]])
    k = KCSD2D(ele_pos, pots,
               gdx=0.05, gdy=0.05,
               xmin=-2.0, xmax=2.0,
               ymin=-2.0, ymax=2.0,
               src_type='gauss')
    k.cross_validate()
    #print k.values('CSD')
    #print k.values('POT')
