from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from math import ceil
from scipy.io import loadmat

import numpy as np
PI = np.pi

from neurongeometry import NeuronGeometry
from image2signal import Image2Signal

from map.mapimpl import (AlbersProjectionMap, EquidistantProjectionMap,
                     SphereToSphereMap)

from transform.imagetransform import ImageTransform


class HemisphereNeuron(object):
    """
        stores and transforms position related information
        access and set parameters only through the provided functions
    """
    def __init__(self, eye_to_screen_map, screen_to_2d_map,
                 eyelat, eyelong):

        self._eyelat = eyelat
        self._eyelong = eyelong
        screenlat, screenlong = eye_to_screen_map.map(eyelat, eyelong)
        self._screenlat = screenlat
        self._screenlong = screenlong
        x, y = screen_to_2d_map.map(screenlat, screenlong)
        self._x = x
        self._y = y

    def get_planepoint(self):
        return (self._x, self._y)

    def get_screenpoint(self):
        return (self._screenlat, self._screenlong)

    def append_screenpoint(self, screenlats, screenlongs):
        """ appends neuron's screen position to the respective parameters """
        screenlats.append(self._screenlat)
        screenlongs.append(self._screenlong)


class HemisphereOmmatidium(object):
    # static variables (Don't modify)
    _rscreen = 10
    # allows easy change to another map
    MAP_SCREEN = AlbersProjectionMap(_rscreen)

    def __init__(self, id, lat, long, reye):
        self.id = id
        self._lat = lat
        self._long = long

        self._reye = reye
        self._neurons = []
        self._screenlats = [0]*7
        self._screenlongs = [0]*7

    def add_photoreceptor(self, direction, rel_pos):
        """ direction: the direction photoreceptor will be facing
            rel_pos: the id of relative position of photoreceptor
            6       1
                0
            5       2
                4
                    3
            [the direction of photoreceptor 1 should be the direction 
             that neighbor at position 5 faces and the same applies 
             to all the others]
        """
        reye = self._reye
        rscreen = self._rscreen

        # eye to screen
        mapeye = SphereToSphereMap(reye, rscreen, direction)
        # screen to xy plane
        mapscreen = self.MAP_SCREEN

        neuron = HemisphereNeuron(mapeye, mapscreen, self._lat, self._long)
        self._neurons.append(neuron)

        # update screenpoints
        neuron_point = neuron.get_screenpoint()
        self._screenlats[rel_pos] = neuron_point[0]
        self._screenlongs[rel_pos] = neuron_point[1]

    def get_direction(self):
        return (self._lat, self._long)

    def get_eyepoint(self):
        return (self._lat, self._long)

    def get_screenpoints(self):
        return (self._screenlats, self._screenlongs)
        
    def get_R1toR6points(self):
        return (self._screenlats[1:], self._screenlongs[1:])



class EyeGeomImpl(NeuronGeometry, Image2Signal):
    # used by static and non static methods and should
    # be consistent among all of them
    OMMATIDIUM_CLS = HemisphereOmmatidium
    DEFAULT_INTENSITY = 0
    MARGIN = 10

    def __init__(self, nrings, reye=1):
        """ map to sphere based on a 2D hex geometry that is closer to a circle
            e.g for one ring there will be 7 neurons arranged like this:
                1
             2     6
                0
             3     5
                4
            Every other ring will have +6 neurons

            nrings: number of rings
            r_eye: radius of eye hemisphere
                   (radius of screen is fixed to 10 right now)
        """
        self._nrings = nrings
        self._reye = reye

        self._nommatidia = self._get_globalid(nrings+1, 0)
        self._ommatidia = []
        self._neighborslist = []
        self._init_neurons()

    @staticmethod
    def _get_globalid(ring, local_id):
        """ Gets a unique id of position based on the ring
            it belongs and its relative id in the ring
            e.g the first rings have local ids
            0 (ring 0)
            0 1 2 3 4 5 (ring 1)
            0 1 2 3 ...
            and global ids
            0
            1 2 3 4 5 6
            7 8 9 ...
        """
        if ring == 0:
            return 0
        else:
            return 3*(ring-1)*ring + 1 + (local_id % (6*ring))

    def _get_neighborgids(self, lid, ring):
        """ Gets global ids of neighbors in the following order (see also 
            RFC2 figure 2)
            in neigbors
            (here x is cartridge and gets inputs from numbered neighbors)
            3
                4
            2       5
                x
            1       6
            ---------
            out neigbors
            (here x is ommatidium and sends output to numbered neighbors)
            6       1
                x
            5       2
                4
                    3
        """
        in_neighborgids = [0]*6
        out_neighborgids = [0]*6
        # note lid is from 0 to 6*ring-1
        quot_ring, res_ring = divmod(lid, ring)

        # **** in id1 out id5 ****
        if (quot_ring == 0) or (quot_ring == 1) or \
                ((quot_ring == 2) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid+1)
        elif ((quot_ring == 2) and (res_ring > 0)) or \
                ((quot_ring == 3) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)
        elif ((quot_ring == 3) and (res_ring > 0)) or \
                (quot_ring == 4):
            id = self._get_globalid(ring-1, lid-4)
        elif (quot_ring == 5):
            id = self._get_globalid(ring, lid+1)

        in_neighborgids[0] = id
        out_neighborgids[4] = id

        # **** in id2 out id6 ****
        if (quot_ring == 0):
            id = self._get_globalid(ring, lid+1)
        elif (quot_ring == 1) or (quot_ring == 2) or \
                ((quot_ring == 3) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid+2)
        elif ((quot_ring == 3) and (res_ring > 0)) or \
                ((quot_ring == 4) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)
        elif ((quot_ring == 4) and (res_ring > 0)) or \
                (quot_ring == 5):
            id = self._get_globalid(ring-1, lid-5)

        in_neighborgids[1] = id
        out_neighborgids[5] = id

        # **** in id3 ****
        if ((quot_ring == 0) and (res_ring < ring-1)):
            id = self._get_globalid(ring-1, lid+1)
        elif ((quot_ring == 0) and (res_ring == ring-1)):
            id = self._get_globalid(ring, lid+2)
        elif (quot_ring == 1):
            id = self._get_globalid(ring+1, lid+3)
        elif (quot_ring == 2) or ((quot_ring == 3) and (res_ring == 0)):
            id = self._get_globalid(ring+2, lid+5)
        elif ((quot_ring == 3) and (res_ring > 0)) or \
                ((quot_ring == 4) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid+2)
        elif ((quot_ring == 4) and (res_ring == 1)) or \
                ((quot_ring == 5) and (res_ring == 0) and (ring == 1)):
            id = self._get_globalid(ring, lid-2)
        elif ((quot_ring == 4) and (res_ring > 1)) or \
                ((quot_ring == 5) and (res_ring == 0)):
            id = self._get_globalid(ring-1, lid-6)
        elif ((quot_ring == 5) and (res_ring > 0)):
            id = self._get_globalid(ring-2, lid-11)

        in_neighborgids[2] = id

        # **** out id3 ****
        if ((quot_ring == 0) and (res_ring == 0)):
            id = self._get_globalid(ring+2, lid-1)  # lid = 0 -> lid-1=-1 ->
                                                    # 6*(ring+2)-1
        elif ((quot_ring == 0) and (res_ring > 0)) or \
                ((quot_ring == 1) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid-1)
        elif ((quot_ring == 1) and (res_ring == 1)) or \
                ((quot_ring == 2) and (res_ring == 0) and (ring == 1)):
            id = self._get_globalid(ring, lid-2)
        elif ((quot_ring == 1) and (res_ring > 1)) or \
                ((quot_ring == 2) and (res_ring == 0)):
            id = self._get_globalid(ring-1, lid-3)
        elif ((quot_ring == 2) and (res_ring > 0)):
            id = self._get_globalid(ring-2, lid-5)
        elif ((quot_ring == 3) and (res_ring < ring-1)):
            id = self._get_globalid(ring-1, lid-2)
        elif ((quot_ring == 3) and (res_ring == ring-1)):
            id = self._get_globalid(ring, lid+2)
        elif (quot_ring == 4):
            id = self._get_globalid(ring+1, lid+6)
        elif (quot_ring == 5):
            id = self._get_globalid(ring+2, lid+11)

        out_neighborgids[2] = id

        # **** in id4 ****
        if (quot_ring == 0):
            id = self._get_globalid(ring-1, lid)
        elif (quot_ring == 1):
            id = self._get_globalid(ring, lid+1)
        elif (quot_ring == 2) or (quot_ring == 3) or \
                ((quot_ring == 4) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid+3)
        elif ((quot_ring == 4) and (res_ring > 0)) or \
                ((quot_ring == 5) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)
        elif ((quot_ring == 5) and (res_ring > 0)):
            id = self._get_globalid(ring-1, lid-6)

        in_neighborgids[3] = id
        
        # **** out id4 ****
        if (quot_ring == 0) or \
                ((quot_ring == 1) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid)
        elif ((quot_ring == 1) and (res_ring > 0)) or \
                ((quot_ring == 2) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)
        elif ((quot_ring == 2) and (res_ring > 0)) or \
                (quot_ring == 3):
            id = self._get_globalid(ring-1, lid-3)
        elif (quot_ring == 4):
            id = self._get_globalid(ring, lid+1)
        elif (quot_ring == 5):
            id = self._get_globalid(ring+1, lid+6)

        out_neighborgids[3] = id

        # **** in id5 out id1 ****
        if ((quot_ring == 0) and (res_ring > 0)) or \
                (quot_ring == 1):
            id = self._get_globalid(ring-1, lid-1)
        elif (quot_ring == 2):
            id = self._get_globalid(ring, lid+1)
        elif (quot_ring == 3) or (quot_ring == 4) or \
                ((quot_ring == 5) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid+4)
        elif ((quot_ring == 5) and (res_ring > 0)) or \
                ((quot_ring == 0) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)

        in_neighborgids[4] = id
        out_neighborgids[0] = id

        # **** in id6 out id2 ****
        if ((quot_ring == 0) and (res_ring == 0)):
            id = self._get_globalid(ring+1, lid-1)
        elif ((quot_ring == 0) and (res_ring > 0)) or \
                ((quot_ring == 1) and (res_ring == 0)):
            id = self._get_globalid(ring, lid-1)
        elif ((quot_ring == 1) and (res_ring > 0)) or \
                (quot_ring == 2):
            id = self._get_globalid(ring-1, lid-2)
        elif (quot_ring == 3):
            id = self._get_globalid(ring, lid+1)
        elif (quot_ring == 4) or (quot_ring == 5):
            id = self._get_globalid(ring+1, lid+5)

        in_neighborgids[5] = id
        out_neighborgids[1] = id

        return (in_neighborgids, out_neighborgids)

    def _init_neurons(self):
        nrings = self._nrings
        reye = self._reye
        ommatidium_cls = self.OMMATIDIUM_CLS
        ommatidia = self._ommatidia
        neighborslist = self._neighborslist

        # the first neuron is a special case
        ommatid = 0
        lat = long = 0
        ommatidium = ommatidium_cls(ommatid, lat, long, reye)
        ommatidium.add_photoreceptor((lat, long), 0)

        ommatidia.append(ommatidium)
        neighborslist.append([ommatidium])

        for ring in range(nrings + 2):
            # lid is local id
            # see _get_globalid method docstring
            ringP1 = ring + 1
            for lid in range(6*ringP1):
                self._update_ommatidia(ringP1, lid)
                self._update_neighbors(ringP1, lid)

    def _update_ommatidia(self, ring, lid):
        nrings = self._nrings
        reye = self._reye
        ommatidia = self._ommatidia
        ommatidium_cls = self.OMMATIDIUM_CLS

        lat = (ring/(nrings + 2))*(PI/2)  # lat: 0 to pi/2,
                                          # but we don't map near pi/2
        long = (lid/(6*ring))*2*PI - PI   # long: -pi to pi

        # if ommatidium is outside the range of rings,
        # construct it
        if ring > nrings:
            ommatidium = ommatidium_cls(-1, lat, long, reye)
        else:
            gid = self._get_globalid(ring, lid)
            ommatidium = ommatidium_cls(gid, lat, long, reye)
            ommatidium.add_photoreceptor((lat, long), 0)

        ommatidia.append(ommatidium)

    def _update_neighbors(self, ring, lid):
        nrings = self._nrings
        nommatidia = self._nommatidia
        ommatidia = self._ommatidia
        neighborslist = self._neighborslist

        gid = self._get_globalid(ring, lid)
        ommatidium = ommatidia[gid]

        # out neighbors (neighbors to send the output to
        #                from current ommatidium)
        # in neighbors (neighbors that current ommatidium receives input from )
        # neighborslist has the out neighbors
        # for the relative position parameter check the order that 
        # the neighbors are returned by _get_neighborgids 
        if ring > nrings:
            in_neighborgids, out_neighborgids = \
                self._get_neighborgids(lid, ring)
            for i, neighborgid in enumerate(in_neighborgids):
                if neighborgid < nommatidia:
                    neighborommat = ommatidia[neighborgid]
                    relative_neighborpos = i + 1
                    neighborommat.add_photoreceptor(ommatidium.get_direction(), 
                                                    relative_neighborpos)
                    neighborslist[neighborgid].append(ommatidium)
        else:
            neighbors = [ommatidium]
            in_neighborgids, out_neighborgids = \
                self._get_neighborgids(lid, ring)
            for i, neighborgid in enumerate(in_neighborgids):
                if neighborgid < gid:
                    neighborommat = ommatidia[neighborgid]
                    relative_neighborpos = i + 1
                    neighborommat.add_photoreceptor(ommatidium.get_direction(),
                                                    relative_neighborpos)
                    neighborslist[neighborgid].append(ommatidium)
            for i, neighborgid in enumerate(out_neighborgids):
                if neighborgid < gid:
                    neighborommat = ommatidia[neighborgid]
                    relative_neighborpos = 5 - i
                    ommatidium.add_photoreceptor(neighborommat.get_direction(),
                                                 relative_neighborpos)
                    neighbors.append(neighborommat)

            neighborslist.append(neighbors)

    def get_neighbors(self):
        """
            neighbors are defined according to the superposition rule
            returns: a list of lists of neighbors, the entries in the initial
                     list are as many as the ommatidia and contain a list of
                     the neighboring ommatidia in no particular order except
                     the first entry that is the reference ommatidium
        """
        return self._neighborslist

    def get_positions(self, config={'coord': 'spherical', 'include': 'center',
                                    'add_dummy': True }):
        """ returns projected positions of photoreceptors
            config: configuration dictionary
                    keys
                    coord: "spherical"(default), returns
                           a tuple of 2 lists (latitudes, longitudes)
                           "cartesian3D", returns a tuple of 3 lists
                           (x, y, z)
                           "cartesian2D", returns a tuple of 2 lists
                           (x, y)
                    include: 'all', 'R1toR6' or 'center'
                    add_dummy: if True(default) 
                               adds 2 more levels of dummy neurons.
                               Useful for superposition rule.
            returns: tuple of lists depending on coordinate type.
                     Each entry in the lists corresponds to a photoreceptor.
                     The photoreceptors of the same ommatidium are consecutive.
                     The order of their positions is 
                     6       1
                         0
                     5       2
                         4
                             3
                     in case of 'center' only 0 is returned and in case of
                     'R1toR6' all others in numerical order
        """
        try:
            coord = config['coord']
            valid_values = ["spherical", "cartesian3D", "cartesian2D"]
            if coord not in valid_values:
                raise ValueError("coord attribute must be one of %s" % ", "
                                 .join(str(x) for x in valid_values))
        except KeyError:
            coord = "spherical"

        try:
            include = config['include']
        except KeyError:
            include = 'center'
        
        try:
            add_dummy = config['add_dummy']
        except KeyError:
            add_dummy = True

        latitudes = []
        longitudes = []

        if include == 'all':
            for ommatidium in self._ommatidia:
                if add_dummy or ommatidium.id != -1:
                    screenlats, screenlongs = ommatidium.get_screenpoints()
                    latitudes.extend(screenlats)
                    longitudes.extend(screenlongs)
        elif include == 'R1toR6':
            for ommatidium in self._ommatidia:
                if add_dummy or ommatidium.id != -1:
                    screenlats, screenlongs = ommatidium.get_R1toR6points()
                    latitudes.extend(screenlats)
                    longitudes.extend(screenlongs)
        else:
            for ommatidium in self._ommatidia:
                if add_dummy or ommatidium.id != -1:
                    eyelat, eyelong = ommatidium.get_eyepoint()
                    latitudes.append(eyelat)
                    longitudes.append(eyelong)

        if coord == "spherical":
            return (np.array(latitudes), np.array(longitudes))
        elif coord == "cartesian3D":
            nplatitudes = np.array(latitudes)
            nplongitudes = np.array(longitudes)
            sinlats = np.sin(nplatitudes)
            coslats = np.cos(nplatitudes)
            sinlongs = np.sin(nplongitudes)
            coslongs = np.cos(nplongitudes)
            return (sinlats*coslongs, sinlats*sinlongs, coslats)
        elif coord == "cartesian2D":
            nplatitudes = np.array(latitudes)
            nplongitudes = np.array(longitudes)
            r2d = nplatitudes/(PI/2)
            sinlongs = np.sin(nplongitudes)
            coslongs = np.cos(nplongitudes)
            return (r2d*coslongs, r2d*sinlongs)

    def get_intensities(self, file, config={}):
        """ file: mat file is assumed but in case more file formats need to be
                  supported an additional field should be included in config
            config: {'still_image': True(default)/False, 
                     'steps':<simulation steps>,
                     'dt':<time step>, 'output_file':<filename>}
            returns: numpy array with with height the number of simulation
                     steps and width the number of neurons.
                     The order of neurons is the same as that returned 
                     in get_positions, with 'R1toR6' option for 'include'
                     configuration parameter
        """
        try:
            dt = config['dt']
        except KeyError:
            dt = 1e-4

        try:
            time_steps = config['steps']
        except KeyError:
            time_steps = 1000

        try:
            still_image = config['still_image']
        except KeyError:
            still_image = True
            
        try:
            # TODO
            output_file = config['output_file']
        except KeyError:
            output_file = None

        mat = loadmat(file)
        try:
            image = np.array(mat['im'])
        except KeyError:
            print('No variable "im" in given mat file')
            print('Available variables (and meta-data): {}'.format(mat.keys()))

        # photons were stored for 1ms
        image *= (dt/1e-3)

        h_im, w_im = image.shape
        transform = ImageTransform(image)

        # screen positions
        # should be much more than the number of photoreceptors
        # shape (20, 3)*self._nrings
        screenlat, screenlong = np.meshgrid(np.linspace(0, PI/2,
                                                        3*self._nrings),
                                            np.linspace(-PI, PI,
                                                        20*self._nrings))

        mapscreen = self.OMMATIDIUM_CLS.MAP_SCREEN
        # plane positions
        # shape (20, 3)*self._nrings
        mx, my = mapscreen.map(screenlat, screenlong)   # map from spherical
                                                        # grid to plane

        # photoreceptor positions
        photorlat, photorlong = self.get_positions({'coord': 'spherical',
                                                    'include': 'R1toR6',
                                                    'add_dummy': False})

        if still_image:
            mx = mx - mx.min()  # start from 0
            my = my - my.min()
            mx *= h_im/mx.max()  # scale to image size
            my *= w_im/my.max()

            # shape (20, 3)*self._nrings
            transimage = transform.interpolate((mx, my))
            
            intensities = self._get_intensities(transimage, photorlat, 
                                                photorlong, screenlat, 
                                                screenlong)
            intensities = np.tile(intensities, (time_steps, 1))
        else:
            intensities = np.empty((time_steps, len(photorlat)), 
                                   dtype='float32')
            mx = mx - mx.min()  # start from 0
            my = my - my.min()
            for i in range(time_steps):
                mx = mx + 2*np.random.random() - 1  # move randomly
                my = my + 2*np.random.random() - 1  # between -1 and 1
                mxi_max = mx.max()
                if mxi_max > h_im:
                    mx = mx - 2*(mxi_max-h_im)
                mxi_min = mx.min()
                if mxi_min < 0:
                    mx = mx - 2*mxi_min

                myi_max = my.max()
                if myi_max > w_im:
                    my = my - 2*(myi_max-w_im)
                myi_min = my.min()
                if myi_min < 0:
                    my = my - 2*myi_min
                
                
                transimage = transform.interpolate((mx, my))
                intensities[i] = self._get_intensities(transimage, photorlat, 
                                                       photorlong, screenlat, 
                                                       screenlong)

        # get interpolated image values on these positions

        return intensities

    def _get_intensities(self, transimage, photorlat, photorlong,
                         screenlat, screenlong):
    
        intensities = np.empty(len(photorlat), dtype='float32')
        # shape (20, 3)*self._nrings
        # h meridians, w parallels
        h_tim, w_tim = transimage.shape
            
        for i, (lat, long) in enumerate(zip(photorlat, photorlong)):

            # position in grid (float values)
            parallelf = (w_tim - 1)*lat/(PI/2)  # float value
            meridianf = (h_tim - 1)*(long + PI)/(2*PI)  # float value

            # for each photoreceptor point find indexes of
            # nxn closest points on grid (int values)
            indlat, indlong = self.get_closest_indexes(parallelf, meridianf,
                                                       min1=0, min2=0, 
                                                       max1=h_tim, 
                                                       max2=w_tim, 
                                                       n=2)
            try:
                pixels = transimage[indlong, indlat]  # nxn np array
            except IndexError:
                print('Array size is {}'.format(transimage.shape))
                print('Indexes are {} and {}'.format(indlat, indlong))
                raise

            weights = self.get_gaussian_sphere(screenlat[indlong, indlat],
                                               screenlong[indlong, indlat],
                                               lat, long)
            # works with >=1.8 numpy
            intensities[i] = np.sum(pixels*weights)

        return intensities
            
            
    
    @staticmethod
    def get_closest_indexes(f1, f2, min1, min2, max1, max2, n):
        """ Given a point (f1, f2) return nxn closest points in the box
            [min1, min2, max1, max2]
        """
        ind1 = np.linspace(np.floor(f1)+(1-n/2), np.ceil(f1)+(-1+n/2), n)\
            .astype(int)
        ind2 = np.linspace(np.floor(f2)+(1-n/2), np.ceil(f2)+(-1+n/2), n)\
            .astype(int)
        ind1 = np.minimum(ind1, max1)
        ind2 = np.minimum(ind2, max2)

        ind1 = np.maximum(ind1, min1)
        ind2 = np.maximum(ind2, min2)
        return np.meshgrid(ind1, ind2)

    @staticmethod
    def get_gaussian_sphere(lats, longs, reflat, reflong):
        """ Computes gaussian function on sphere at points (lats, longs),
            with a given center (reflat, reflong).
            Values are normalized so that they sum up to 1.
            Kappa is 100
            
            see also:
            http://en.wikipedia.org/wiki/Von_Mises%E2%80%93Fisher_distribution
        """
        #
        KAPPA = 100
        # inner product of reference point with other points translated to
        # spherical coordinates
        in_prod = np.sin(lats)*np.sin(reflat)*np.cos(reflong-longs) \
            + np.cos(lats)*np.cos(reflat)
        func3 = np.exp(KAPPA*in_prod)
        # ignore constant factor C_p and normalize so that everything sums to 1
        return func3/np.sum(func3)

    def visualise_output(self, output, file, config=None):
        pass

if __name__ == '__main__':
    from mpl_toolkits.mplot3d import Axes3D
    from matplotlib import cm
    from matplotlib.collections import LineCollection
    import matplotlib.pyplot as plt
    import time

    N_RINGS = 1
    STILL_IMAGE = True
    
    print('Initializing geometry')
    hemisphere = EyeGeomImpl(N_RINGS)
    print('Getting positions')
    positions = hemisphere.get_positions({'coord': "cartesian3D"})
    print('Getting neighbors')
    neighbors = hemisphere.get_neighbors()

    print('Getting intensities')
    start_time = time.time()
    intensities = hemisphere.get_intensities('image1.mat', 
                                             {'still_image': STILL_IMAGE})
    print("--- Duration {} seconds ---".format(time.time() - start_time))

    print('Setting up plot 1: Ommatidia on 3D sphere')
    fig1 = plt.figure()
    ax1 = fig1.gca(projection='3d')
    ax1.set_title('Ommatidia on 3D sphere')
    ax1.plot_trisurf(positions[0], positions[1], positions[2],
                     cmap=cm.coolwarm, linewidth=0.2)

    #

    print('Setting up plot 2: a) 2d projection of ommatidia and their'
          ' connections with neighbors, b) projections of screen positions')
    fig2 = plt.figure()
    ax2_1 = fig2.add_subplot(121)
    ax2_1.set_title('2d projection of ommatidia and their'
                    ' connections with neighbors')

    xpositions, ypositions = hemisphere.get_positions({'coord': "cartesian2D"})

    segmentlist = []
    for neighborlist in neighbors:
        original = neighborlist[0]
        original = original.id
        for neighbor in neighborlist[1:]:
            neighbor = neighbor.id
            if (neighbor != -1):  # some edges are added twice
                segmentlist.append([[xpositions[original],
                                     ypositions[original]],
                                    [xpositions[neighbor],
                                     ypositions[neighbor]]])

    linesegments = LineCollection(segmentlist, linestyles='solid')
    ax2_1.add_collection(linesegments)
    ax2_1.set_xlim((-1, 1))
    ax2_1.set_ylim((-1, 1))

    ax2_2 = fig2.add_subplot(122)
    ax2_2.set_title('2d projection of ommatidia and their'
                    ' projections of screen positions')
    xpositions, ypositions = hemisphere.get_positions({'coord': "cartesian2D",
                                                       'include': 'all',
                                                       'add_dummy': False})

    ax2_2.scatter(xpositions, ypositions)

    print('Setting up plot 3: greyscale image and intensities')

    mat = loadmat('image1.mat')
    try:
        image = np.array(mat['im'])
    except KeyError:
        print('No variable "im" in given mat file')
        print('Available variables (and meta-data): {}'.format(mat.keys()))

    fig3 = plt.figure()
    ax3_1 = fig3.add_subplot(121)
    ax3_1.set_title('greyscale image')
    ax3_1.imshow(image, cmap=cm.Greys_r)

    print(intensities.shape)
    print(intensities)
    ax3_2 = fig3.add_subplot(122)
    ax3_2.set_title('intensities')
    xpositions, ypositions = hemisphere.get_positions({'coord': "cartesian2D",
                                                       'include': 'R1toR6',
                                                       'add_dummy': False})
    print(xpositions.shape)

    ax3_2.scatter(xpositions, -ypositions, c=intensities[1], cmap=cm.gray, s=5,
                  edgecolors='none')

    plt.show()
