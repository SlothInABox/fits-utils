#! /usr/bin/env python

"""
fits-utils module

This module contains various functions for the reduction, alignment and stacking
of raw astronomical frames using the FITS file formatting standard. It is an
extension of the astropy module, and utilises many of its basic functions to
perform more complicated operations.

The raw files are stored in the "dat/" folder, which is read-only; science
frames are written to and read from in the "sci/" folder; temporary files
(including master dark and flat fields) are written to and read from the "tmp/"
directory; and stacked images are written to and read from the "sta/" directory.

This module utilises the configparser module in order to generate a "config.ini"
file. This file can be populated by the user with a target ID, standard star ID,
and observing bands. The module can then use these parameters to parse the
"raw/" directory and sort FITS files into lists with specific integration times
and bands. The images can then be reduced and written out to FITS files.

By convention, imported:

import fits-utils as fu
"""

import math as m
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from scipy.stats import mode
from pathlib import Path
from astropy.io import fits
from os import walk
import configparser

def get_lists(dir):
    """
    Sorts fits files into lists.
    Function to create lists of darks, flats, targets, and standard stars. Each
    list contains a dictionary and is constructed by the add_to_list method.
    The configparser package is used to read a .ini file containing settings
    that may be changed by the user in a text editor.

    The function loops through the specified directory and assigns .fits files
    to the lists if they match data in the config.ini file.

    Args:
        dir (str): The path of the directory to be used.

    Returns:
        dark_list (list): The list of "dark" .fits files.
        flat_list (list): The list of "flat" .fits files.
        target_list (list): The list of "target" .fits files.
        standard_star_list (list): The list of "standard stars" .fits files.
    """
    #: list: Initially empty lists for containing dicts
    dark_list = []
    flat_list = []
    target_list = []
    standard_star_list = []
    # Why is this function defined inside another? ~Wheaton
    def add_to_list(array, filename, **kwargs):
        """
        Adds file data to lists of dictionaries.

        Function to construct a dictionary for a fits file containing a filename
        key and keys for other optional information: integration time and band.
        The dictionary is appended to a specific list.

        Args:
            array (list): The list to append the dictionary to.
            filename (str): The name of the fits file.
            **kwargs: Arbitrary keyword arguments.
        """
        #: dict of str: Holds keys and values for filename and optional keys
        new_dict = {
            "filename": filename
        }
        for key, value in kwargs.items():
             new_dict[key] = value
        array.append(new_dict)
    #: ConfigParser: Contains setup data stored in .ini file.
    config = configparser.ConfigParser()
    config.read("config.ini")
    data_settings = config["DATA SETTINGS"]
    _, _, filenames = next(walk(dir), (None, None, []))
    for filename in filenames:
        if filename.endswith(".fits"):
            name_str = filename.split("_")
            if name_str[0].lower() == "dark":
                add_to_list(dark_list, filename, integration_time = name_str[1])
            elif name_str[0].lower() == "flat":
                add_to_list(flat_list, filename, integration_time = name_str[2], band = name_str[1])
            elif name_str[0].lower() == data_settings["standard star a"] or name_str[0].lower() == data_settings["standard star b"]:
                add_to_list(standard_star_list, filename, integration_time = name_str[2], band = name_str[1])
            elif name_str[0].lower() == data_settings["target id"]:
                add_to_list(target_list, filename, integration_time = name_str[2], band = name_str[1])
    return dark_list, flat_list, target_list, standard_star_list

def load_fits(**kwargs):
    """
    Receives a directory path and .fits filename parameters. Parses the
    directory for files matching the naming parameters and loads matched files
    into a list of astropy.fits objects. Returns the list.
    """
    path = kwargs.get("path")
    # year = kwargs.get("year")
    band = kwargs.get("band")
    target_id = kwargs.get("target")
    images = []
    for root, dir, files in walk(path):
        for filename in files:
            if "left" in filename:
                pass
            elif "attempt" in filename:
                pass
            elif target_id in filename and band in filename:
                int_time = filename.split("_")[2][:-1]
                print(target_id, band, int_time, " matched ", filename)
                # hdul = fits.open(root + filename)
                # hdul[0].header["EXPTIME"] = int_time
                # hdul[0].header["TARGTID"] = target_id
                # hdul[0].header["FILENME"] = filename
                # images.append(hdul)
                with fits.open(root+filename) as hdul:
                    new_image = {}
                    new_image["int_time"] = int_time
                    new_image["target"] = target_id
                    new_image["filename"] = filename
                    new_image["data"] = hdul[0].data
                    images.append(new_image)

    # Check that all the sizes of the loaded fits objects match.
    x_sizes, y_sizes = [], []
    for image in images:
        x_sizes.append(image['data'].shape[0])
        y_sizes.append(image['data'].shape[1])
    # If all fits object dimensions match, return the existing list of objects.
    if all(x==x_sizes[0] for x in x_sizes) and all(y==y_sizes[0] for y in y_sizes):
        return(images)
    # If not, cast them into arrays of zeros with matching dimensions and copy
    # the header data over to the newly created fits objects.
    else:
        print("Imported image dimensions do not match! Framing with zeros.")
        framed_images = []
        for image in images:
            framed_image = {}
            framed_image['data'] = np.zeros((max(x_sizes),max(y_sizes)))
            framed_image['data'][:image['data'].shape[0],:image['data'].shape[1]] = image['data']
            # hdul = fits.HDUList([fits.PrimaryHDU(framed_image)])
            framed_image["int_time"] = image["int_time"]
            framed_image["target"] = image["target"]
            framed_image["filename"] = image["filename"]
            framed_images.append(hdul)
        return(framed_images)

def median(list):
    """
    DEPRECATED
    Returns the median value of a given list. Used for averaging frames without
    the influence of outlier count values.
    """
    list.sort()
    if len(list)%2 == 0:
        index = int(m.floor(len(list)/2)) - 1
        median = int(m.floor((list[index] + list[index+1])/2))
    if len(list)%2 == 1:
        index = int(m.ceil(len(list)/2))
        median = list[index]
    return(median)

def average_frame(filelist, **kwargs):
    """
    Recieves a list of .fits images and returns either their mean or median as
    a HDUList object, depending upon the value of keyword argument "average=".
    Uses either the astropy or the pyraf module depending upon the value of the
    keyword argument "mode=".

    Args:
        filelist (list): list of HDUList.
        **kwargs: Arbitrary keyword arguments.
    Returns:
        average (HDUList): object containing HDUList that can be written to a
            file.
    """
    if kwargs.get("mode") == "astropy":
        if kwargs.get("average") == "mean":
            for file_object in filelist:
                average += file_object
            average = average / len(filelist)
        if kwargs.get("average") == "median":
            # Check that all the images are of the same dimensions.
            ra_pix = len(filelist[0])
            dec_pix = len(filelist[0][0])
            for file_object in filelist:
                if ra_pix != len(file_object):
                    print("Warning! Image dimensions do not match!\n")
                    break
                if dec_pix != len(file_object[0]):
                    print("Warning! Image dimensions do not match!\n")
                    break
            # Initialise empty array and populates it with median values.
            average = np.zeros((ra_pix, dec_pix))
            for i in range(ra_pix):
                for j in range(dec_pix):
                    counts = []
                    for file_object in filelist:
                        counts.append(file_object[i][j])
                    average[i][j] = median(counts)
        return average
    if kwargs.get("mode") == "pyraf":
        # lol, don"t do this.
        return average

def write_out_fits(image, filename):
    """
    Creates a header for an ndarray of reduced data and then creates a new fits
    file of this data.

    Args:
        image (ndarray): reduced data to be written to fits file.
        filename (string): name (and location) of new fits file.
    """
    hdul = fits.HDUList([fits.PrimaryHDU(image)])
    hdul.writeto(filename, overwrite=True)

def normalise_flat(flat_array):
    """
    Normalises the data in a flat frame by dividing each data value by the modal
    value.

    Args:
        flat_array (ndarray): flat data to be normalised.
    Returns:
        normalised_flat (ndarray): new normalised flat data.
    """
    normalised_flat = flat_array / mode(flat_array, axis=None)[0][0]
    return normalised_flat

def max_value_centroid(image_data, **kwargs):
    """
    Receives an image array and returns the coordinates of the brightest pixel
    in that image array.

    Args:
        image_data (2darray): The image array to be searched.
    Returns:
        (x_max,y_max) (tuple): pixel coordinates of the maximum value of the
            image array.
    """
    x_max, y_max = np.where(image_data == np.amax(image_data))
    # plt.imshow(cutout)
    # plt.scatter(x_max, y_max, s=2, c='red', marker='o')
    # plt.show()
    return((x_max[0], y_max[0]))

def threshold_centroid(cutout, **kwargs):
    """
    DEPRECATED
    Returns the weighted mean centroid of values above 2/3 the maximum value in
    a cutout of an array.
    """
    x_sum = np.sum(cutout, axis=0)
    y_sum = np.sum(cutout, axis=1)
    x_fwh = np.where(x_sum >= 0.67 * max(x_sum))
    y_fwh = np.where(y_sum >= 0.67 * max(y_sum))
    x_avg = np.average(x_fwh[0], weights=x_sum[x_fwh])
    y_avg = np.average(y_fwh[0], weights=y_sum[y_fwh])
    # plt.imshow(cutout)
    # plt.scatter(x_avg, y_avg, s=2, c='red', marker='o')
    # plt.show()
    return((int(np.floor(x_avg)), int(np.floor(y_avg))))

def custom_roll(array, axis=0):
    """Getting sum of nearest neighbours for each value in an array.

    For each value in an ndarray, sums the nearest neighbours around that
    position for one axis. Pads array with zeroes, aligns array with dstack and
    roll.

    Args:
        array (ndarray): Array to be passed over.
        axis (int): Specific axis to be rolled over. Defaults to 0.

    """
    no = 3
    array = array.T if axis==1 else array
    padding = np.zeros((no-1, array.shape[1]))
    array = np.concatenate([array, padding], axis=0)
    neighbours = np.dstack([np.roll(array, i, axis=0) for i in range(no)])
    array = neighbours.sum(2)[1:-1, :]
    array = array.T if axis==1 else array
    return array

def create_mask(image_data, **kwargs):
    # Offset image so that all values are positive
    offset_data = image_data + np.abs(np.amin(image_data))
    mask = np.empty(offset_data.shape)
    # Invalidate values based on the value of their neighbors (slow).
    # if kwargs.get("condition") == "neighbors":
    #     for i in range(offset_data.shape[0]):
    #         for j in range(offset_data.shape[1]):
    #             try:
    #                 neighbors_sum = offset_data[i-1,j]+offset_data[i+1,j]+offset_data[i,j-1]+offset_data[i,j+1]
    #                 if offset_data[i,j] >= neighbors_sum:
    #                     mask[i,j] = 1
    #                 else:
    #                     mask[i,j] = 0
    #             except IndexError:
    #                 mask[i,j] = 1
    if kwargs.get("condition") == "neighbors":
        sum_of_neighbours = custom_roll(custom_roll(offset_data), axis=1) - offset_data
        mask = offset_data > sum_of_neighbours
    # Invalidate values that fall below a certain threshold (fast).
    if kwargs.get("condition") == "threshold":
        max_value = np.amax(offset_data)
        for i in range(offset_data.shape[0]):
            for j in range(offset_data.shape[1]):
                if offset_data[i,j] <= 0.67 * max_value:
                    mask[i,j] = 1
                else:
                    mask[i,j] = 0
    if "border" in list(kwargs.keys()):
        size = kwargs.get("border")
        mask[:size,:] = 1
        mask[-size:,:] = 1
        mask[:,:size] = 1
        mask[:,-size:] = 1
    return(mask)

def weighted_mean_2D(cutout,**kwargs):
    """
    Recieves an argument of type ndarray and returns a tuple of the weighted
    mean centroid of the object contained in the cutout.

    Args:
        cutout (ndarray): portion of fits full ndarray.
    Returns:
        x_avg (int): weighted mean of x values.
        y_avg (int): weighted mean of y values.
    """
    cutout += np.abs(np.amin(cutout))
    x_sum = np.sum(cutout, axis=0)
    y_sum = np.sum(cutout, axis=1)
    x_avg = np.average(range(x_sum.size), weights=x_sum)
    y_avg = np.average(range(y_sum.size), weights=y_sum)
    # plt.imshow(cutout)
    # plt.scatter(x_avg, y_avg, s=2, c='red', marker='o')
    # plt.show()
    if kwargs.get("floor") == True:
        return((int(np.floor(x_avg)), int(np.floor(y_avg))))
    else:
        return((x_avg, y_avg))

def hybrid_centroid(image_data, **kwargs):
    """
    Recieves an array of image data and returns the pixel coordinates of the
    centroid of the brightest star in the frame. Makes an initial guess at the
    position of the star by finding the maximum value in the array, then
    performs a weighted mean in two dimensions about the guess for finer accuracy.

    Args:
        image_data (2darray): array of image data containing reference star.
        size (int): the radius of the reference star, in pixels. Used to create
            cutout of appropriate size.
    Returns:
        (x_avg,y_avg) (tuple): pixel coordinates of the centroid of the
            brightest star in the image array.
    """
    # plt.imshow(image_data, norm=LogNorm())
    # plt.show()
    size = kwargs.get("size")
    # Attempt to invalidate pixels which may confuse the initial guess.
    if kwargs.get("mask") == True:
        masked_data = np.ma.array(image_data, mask=create_mask(image_data, condition="neighbors", border=size))
        x_max, y_max = max_value_centroid(masked_data)
    # Get the maximum value of the cutout as an initial guess.
    else:
        x_max, y_max = max_value_centroid(image_data)
    # plt.imshow(image_data, norm=LogNorm())
    # plt.show()
    # Create a smaller cutout around the initial guess.
    cutout = np.array(image_data[x_max-size:x_max+size,y_max-size:y_max+size])
    # Get the mean weighted average of the smaller cutout.
    x_new, y_new = weighted_mean_2D(cutout, floor=True)
    # Map the centroid back to coordinates of original cutout.
    x_avg = x_max - size + x_new
    y_avg = y_max - size + y_new
    # plt.imshow(image_data, norm=LogNorm())
    # plt.scatter(x_avg, y_avg, s=2, c='red', marker='o')
    # plt.show()
    return((x_avg, y_avg))

def old_align(image_stack, **kwargs):
    """
    DEPRECATED
    Recieves a list of image arrays and some "cutout" range containing a common
    object to use for alignment of the image stack. Returns a list of image
    arrays of different size, aligned, and with zero borders where the image has
    been shifted.

    Args:
        image_stack (list): frames to be aligned.
        centroid (func_handle): function handle for arbitrary centroiding
            function which returns a position tuple.
    Returns:
        aligned_image_stack (list): new frames that have been aligned and can be
            stacked.
    """
    centroid = kwargs.get("centroid")
    # Get lists of all the x and y centroids.
    x_centroids, y_centroids = [], []
    for image in image_stack:
        x_centroids.append(centroid(image[0].data, size=50)[0])
        y_centroids.append(centroid(image[0].data, size=50)[1])
    x_ref, y_ref = max(x_centroids), max(y_centroids)
    x_max_offset = max(x_centroids) - min(x_centroids)
    y_max_offset = max(y_centroids) - min(y_centroids)
    # Create new list of image arrays with offset.
    aligned_image_stack = []
    for image in image_stack:
        aligned_image = np.zeros((image[0].data.shape[0]+x_max_offset, image[0].data.shape[1]+y_max_offset))
        x_image_offset = x_ref - centroid(image[0].data, size=50)[0]
        y_image_offset = y_ref - centroid(image[0].data, size=50)[1]
        aligned_image[x_image_offset:x_image_offset+image[0].data.shape[0],y_image_offset:y_image_offset+image[0].data.shape[1]] = image[0].data
        aligned_image_stack.append(aligned_image)
    return(aligned_image_stack)

def align(images, **kwargs):
    """
    Recieves a list of image arrays containing a common object to use for
    alignment of the image stack. Returns a list of image arrays of different
    size, aligned, and with zero borders where the image has been shifted.

    Args:
        images (list): Frames to be aligned.

    Returns:
        aligned_images (list): new frames that have been aligned and can be
            stacked.
    """
    # Boolean, whether or not to mask images for hot pixels on the detector.
    mask = kwargs.get("mask")
    # Find the centroid of the reference star in each image.
    x_centroids, y_centroids = [], []
    print("---Beginning Alignment---")
    counter = 0
    for image in images:
        counter += 1
        print("---Finding Centre {} of {}".format(counter, len(images)), end="\r")
        centroid = hybrid_centroid(image['data'], size=50, mask=mask)
        x_centroids.append(centroid[0])
        y_centroids.append(centroid[1])
        image['XCENT'] = centroid[0]
        image['YCENT'] = centroid[1]
    print()
    max_pos = (max(x_centroids), max(y_centroids))
    min_pos = (min(x_centroids), min(y_centroids))
    max_dif = (max_pos[0]-min_pos[0], max_pos[1]-min_pos[1])
    # Create new stack of aligned images using the centroid in each frame.
    aligned_images = []
    for image in images:
        aligned_image = np.zeros((image['data'].shape[0]+max_dif[0], image['data'].shape[1]+max_dif[1]))
        centroid = (image['XCENT'], image['YCENT'])
        disp = (max_pos[0] - centroid[0], max_pos[1] - centroid[1])
        aligned_image[disp[0]:disp[0]+image['data'].shape[0],disp[1]:disp[1]+image['data'].shape[1]] = image['data']
        aligned_images.append(aligned_image)
    print("---Alignment Complete---")
    return aligned_images

def stack(aligned_image_stack):
    """
    Receives a list of aligned images and returns their summation along the axis
    of the list.#

    Args:
        aligned_image_stack (list): aligned frames ready to be stacked.
    Returns:
        stacked_image (2darray): new combined single frame.
    """
    # Check that the aligned images to be stacked have matching dimensions.
    for image in aligned_image_stack:
        if image.shape != aligned_image_stack[0].shape:
            print("Aligned image dimensions do not match!")
            break
    # If all dimensions match, initialise an empty array with those dimensions
    # into which aligned images are stacked.
    stacked_image = np.zeros(aligned_image_stack[0].shape)
    for image in aligned_image_stack:
        stacked_image += image
    return(stacked_image)

def rgb(image_r, image_g, image_b):
    """
        Recieves three arrays of equal size. Maps these values to RGB values
        using the Lupton algorithm and displays the resulting image.
        # TODO: Retrieve the source for this algorithm.
    """
    from astropy.visualization import make_lupton_rgb
    rgb_image = make_lupton_rgb(image_r, image_g, image_b, Q=10, stretch=1000.)
    plt.imshow(rgb_image)
    plt.show()

def reduce_raws(raw_list, master_dark_frame, master_flat_frame, dir):
    """
    Reduces raw images into science images. This function loops through a
    list of raws. Each raw image is dark subtracted and then flat divided.

    Args:
        raw_list (list): Raw ndarray objects.
        master_dark_frame (dict): Dark ndarrays.
        master_flat_frame (dict): Flat ndarrays.
    Returns:
        science_list (list): Reduced ndarray objects.
    """
    #: list of ndarray: Empty list for reduced images.
    science_list = {}
    for raw in raw_list:
        print("Reducing {} of {} images.".format(len(science_list), len(raw_list)), end="\r"),
        with fits.open(dir / raw["filename"]) as hdul:
            #: ndarray: Dark subtracted image data
            ds_data = np.subtract(hdul[0].data, master_dark_frame[raw["integration_time"]])
            science_list[raw["filename"]] = np.divide(ds_data, master_flat_frame[raw["band"]])
    print("\nDone!")
    return science_list