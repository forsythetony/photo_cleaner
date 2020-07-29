#!/usr/bin/env python3
import os
from enum import Enum
import shutil
from shutil import copyfile
import argparse
import yaml
import PIL
from PIL import Image
from math import floor

CONFIG = None
SOURCE_DIR = None
DESTINATION_DIR = None
SKIP_COPY_BACK = True
IMAGE_RESIZE_FACTOR = .7

BASE_OUTPUT_DIR = "output"

IMAGE_INFORMATION_START_INDEX = 6

class ImageType(Enum):
    CORRECTED_FRONT = 1
    ORIGINAL_FRONT = 2
    ORIGINAL_BACK = 3

def load_configuration():
    file = open('config.yml', 'r')
    
    global CONFIG
    CONFIG = yaml.load(file, Loader=yaml.FullLoader)

def setup():
    load_configuration()
    configure_arg_parse()

def set_argument_vars(args):

    global SOURCE_DIR
    global DESTINATION_DIR
    global SKIP_COPY_BACK

    SOURCE_DIR = args.input_directory
    DESTINATION_DIR = args.output_directory
    SKIP_COPY_BACK = args.skip_copy_back

def configure_arg_parse():
    parser = argparse.ArgumentParser(description=CONFIG['about']['description'])

    parser.add_argument(
        '-i', '--input', 
        dest='input_directory', 
        required=True
    )

    parser.add_argument(
        '-o', '--output',
        dest='output_directory',
        required=False,
        default='output'
    )

    parser.add_argument(
        '--skipBack',
        dest='skip_copy_back',
        action='store_true',
        required=False,
        default=False
    )

    args = parser.parse_args()

    set_argument_vars(args)    

"""
    Will pull the full image paths from the source directory
"""
def pull_images_from_directory(images_dir):

    images = []

    for file in os.listdir(images_dir):
        if file.endswith(".jpg"):
            images.append(os.path.join(images_dir, file))

    return sorted(images)

def get_final_path_component(path):
    return os.path.basename(os.path.normpath(path))

def clean_image_id(raw_image_id: str):
    if "." in raw_image_id:
        components = raw_image_id.split('.')
        return int(components[0])
    
    return int(raw_image_id)

def is_string_int(str):
    try:
        int(str)
        return True
    except ValueError:
        return False

def get_image_information_start_index(final_path):
    split_on_period_components = final_path.split('.')

    if len(split_on_period_components) != 2:
        print("When splitting the path component {} on periods I got an unexpected value of {} for the number of components".format(final_path, len(split_on_period_components)))
        return
    
    main_component = split_on_period_components[0]

    main_components_split = main_component.split('_')

    main_comp_len = len(main_components_split)

    info_index = main_comp_len - 1

    for i in range(main_comp_len - 1, -1, -1):
        info_index = i
        curr_component = main_components_split[i]

        if is_string_int(curr_component):
            break

    return info_index

def create_image_record(full_image_path):

    final_path = get_final_path_component(full_image_path)

    final_path_parts = final_path.split('_')

    final_path_parts_length = len(final_path_parts)
    
    image_information_start_index = get_image_information_start_index(final_path)

    # print("The number of path components is {}".format(final_path_parts_length))
    if (final_path_parts_length < image_information_start_index):
        print("The number of final path parts was {}".format(final_path_parts_length))
        print("I don't know what to do with this record...")
        
        return {
            'error': True
        }

    image_id = clean_image_id(final_path_parts[image_information_start_index])

    """
        If we have less than 2 path components (disregarding the album title that FastFoto
        adds) then we know is the original front scan
    """
    if final_path_parts_length - image_information_start_index < 2:
        return {
            'error': False,
            'full_image_path': full_image_path,
            'final_path_component': final_path,
            'image_type': ImageType.ORIGINAL_FRONT,
            'image_id': image_id
        }

    """
        If there is another path component then we know that this image is
        either the upgraded front version or the back
    """
    type_component = final_path_parts[image_information_start_index  + 1]

    if type_component[0] == 'a':
        return {
            'error': False,
            'full_image_path': full_image_path,
            'final_path_component': final_path,
            'image_type': ImageType.CORRECTED_FRONT,
            'image_id': image_id
        }

    if type_component[0] == 'b':
        return {
            'error': False,
            'full_image_path': full_image_path,
            'final_path_component': final_path,
            'image_type': ImageType.ORIGINAL_BACK,
            'image_id': image_id
        }

    print("Found an error")
    print(full_image_path)
    return {
        'error': True
    }

def build_image_precopy_records(records_map):

    ret_val = []

    for key,value in records_map.items():
        total_values = len(value)

        image_record = {
            'image_id': key,
            'front_full_path': None,
            'back_full_path': None
        }

        for v in value:
            if v['image_type'] == ImageType.ORIGINAL_BACK:
                image_record['back_full_path'] = v['full_image_path']
            elif v['image_type'] == ImageType.CORRECTED_FRONT:
                image_record['front_full_path'] = v['full_image_path']
            else:
                if image_record['front_full_path'] == None:
                    image_record['front_full_path'] = v['full_image_path']

        if image_record['front_full_path'] is not None:
            ret_val.append(image_record)

    return ret_val    

def build_image_records(all_images):

    image_records = []
    
    for i in all_images:
        image_records.append(create_image_record(i))

    return image_records

def combine_records(image_records):
    records_map = {}

    for i in image_records:
        image_id = i['image_id']

        if image_id not in records_map:
            records_map[image_id] = []

        records_map[image_id].append(i)

    return records_map

def make_output_directory():
    """
        First let's delete the output directory to make sure
        we're working with a clean slate
    """

    if not os.path.isdir(BASE_OUTPUT_DIR):
        os.mkdir(BASE_OUTPUT_DIR)
    
    global DESTINATION_DIR
    
    DESTINATION_DIR = os.path.join(BASE_OUTPUT_DIR, DESTINATION_DIR)

    if os.path.isdir(DESTINATION_DIR):
        shutil.rmtree(DESTINATION_DIR)

    try:
        os.mkdir(DESTINATION_DIR)
    except OSError:
        print ("Creation of the directory %s failed" % DESTINATION_DIR)
        return

def build_front_destination_path(image_id, max_width):

    front_back_identifier = ""

    if not SKIP_COPY_BACK:
        front_back_identifier = "_front"
    
    image_id_component = str(image_id).zfill(max_width)

    return os.path.join(DESTINATION_DIR, "{}{}.jpg".format(image_id_component, front_back_identifier))

def build_back_destination_path(image_id, max_width):
    image_id_component = str(image_id).zfill(max_width)

    return os.path.join(DESTINATION_DIR, "{}_back.jpg".format(image_id_component))

def get_max_width_for_image_id(image_precopy_records):
    
    max_image_id = max(map(lambda x: x['image_id'], image_precopy_records))

    return len(str(max_image_id))

def get_bytes_string(total_bytes):

    if total_bytes < 1e3:
        return f"{total_bytes} bytes"

    if total_bytes < 1e6:
        kilobytes = total_bytes / 1e3
        return f"{kilobytes:.2f} kb"

    if total_bytes < 1e9:
        megabytes = total_bytes / 1e6
        return f"{megabytes:.2f} mb"

    if total_bytes < 1e12:
        gigabytes = total_bytes / 1e9
        return f"{gigabytes:.2f} gb"

    return f"{total_bytes} bytes"

def resizeAndCopy(source, destination):
    
    if not os.path.exists(source):
        raise Exception(f"An image at path {source} does not exist")

    image_size = os.stat(source).st_size

    print(f"Attempting to resize image at path {source}")
    print(f"Current image size is {get_bytes_string(image_size)}")

    img = Image.open(source)

    image_width = img.size[0]
    image_height = img.size[1]
    
    new_size = (floor(image_width * IMAGE_RESIZE_FACTOR), floor(image_height * IMAGE_RESIZE_FACTOR))

    print(f"Will attempt to resize image from size {img.size} to new size {new_size}")

    img = img.resize(new_size, PIL.Image.ANTIALIAS)

    print(f"Resized image. Saving to {destination}")
    img.save(destination)
    new_image_size = os.stat(destination).st_size
    print(f"New image size is {get_bytes_string(new_image_size)}")


def copy_images(image_precopy_records):
    make_output_directory()

    max_width = get_max_width_for_image_id(image_precopy_records)

    print("Max width id is {}".format(max_width))

    for record in image_precopy_records:

        image_id = record['image_id']

        print("Working on {}".format(record))
        #   Copy the front image
        front_source = record['front_full_path']
        front_destination = build_front_destination_path(image_id, max_width)

        try:
            # shutil.copyfile(front_source, front_destination)
            resizeAndCopy(front_source, front_destination)
        except OSError as e:
            print("Something went wrong when attempting to copy over the front of the following record -> {}".format(record))
            continue

        #   Copy the back image
        back_source = record['back_full_path']
        if back_source is not None and not SKIP_COPY_BACK:
            back_destination = build_back_destination_path(image_id, max_width)
            
            try:
                # shutil.copyfile(back_source, back_destination)
                resizeAndCopy(back_source, back_destination)
            except OSError as e:
                print("Something went wrong when attempting to copy over the back of the following record -> {}".format(record))
                continue

def script_base_dir():
    return os.path.dirname(os.path.realpath(__file__))

def test():

    source_image_path = os.path.join(script_base_dir(), 'test', 'input', 'testImage.jpg')
    destination_image_path = os.path.join(script_base_dir(), 'test', 'output', 'testImageResult.jpg')

    resizeAndCopy(source_image_path, destination_image_path)

def main():
    setup()

    all_images = pull_images_from_directory(SOURCE_DIR)
    
    records = build_image_records(all_images)

    records_map = combine_records(records)

    image_precopy_records = build_image_precopy_records(records_map)

    copy_images(image_precopy_records)

if __name__ == "__main__":
    main()
    # test()
