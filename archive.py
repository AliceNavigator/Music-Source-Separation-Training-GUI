import os
import shutil
import datetime

DEFAULT_SOURCE_FOLDERS = ['separation_results', 'karaoke_results', 'deverb_results', 'denoise_results', 'other_results', 'input']
DEFAULT_DESTINATION_FOLDER = 'archive'


def archive_folders(output_callback=None, source_folders=None, destination_folder=None):
    if output_callback is None:
        output_callback = print
    
    if source_folders is None:
        source_folders = DEFAULT_SOURCE_FOLDERS
    
    if destination_folder is None:
        destination_folder = DEFAULT_DESTINATION_FOLDER

    output_callback("开始归档处理...\n")

    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)
        output_callback(f"创建归档文件夹: {destination_folder}")

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    for folder in source_folders:
        if os.path.exists(folder):
            dest_folder = os.path.join(destination_folder, folder)

            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)
                output_callback(f"\n创建目标文件夹: {dest_folder}")

            for root, dirs, files in os.walk(folder, topdown=True):
                relative_path = os.path.relpath(root, folder)
                dest_dir = os.path.join(dest_folder, relative_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir)

                for file in files:
                    src_file = os.path.join(root, file)
                    dest_file = os.path.join(dest_dir, file)

                    if os.path.exists(dest_file):
                        file_base, file_ext = os.path.splitext(file)
                        new_file_name = f"{file_base}_{timestamp}{file_ext}"
                        dest_file = os.path.join(dest_dir, new_file_name)
                        output_callback(f'【{file_base}】已经存在！将重命名保存为：【{new_file_name}】')

                    shutil.move(src_file, dest_file)
                    output_callback(f"已移动文件: {src_file} -> {dest_file}")

            if folder == 'input':
                for root, dirs, files in os.walk(folder, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                output_callback(f"已清空input文件夹\n")
            else:
                shutil.rmtree(folder)
                output_callback(f"已完成归档: {folder}\n")

    output_callback("归档处理完成")


if __name__ == "__main__":
    archive_folders()