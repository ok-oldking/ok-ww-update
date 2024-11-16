import sys

import os
import shutil
import stat
import subprocess


def run_command(command):
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding='utf-8')
    if result.returncode != 0:
        print(f"Warning: Command '{command}' failed with error:\n{result.stderr.strip()} \n{result.stdout.strip()}")
        raise Exception(f"Command '{command}' failed with error:\n{result.stderr.strip()}")
    return result.stdout.strip()


def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_current_branch():
    return run_command("git rev-parse --abbrev-ref HEAD")


def get_latest_commit_message():
    return run_command("git log -1 --pretty=%B").strip()


def should_skip(item_path, skip_items):
    return os.path.basename(item_path) in skip_items


def main():
    if '--repos' not in sys.argv or '--files' not in sys.argv:
        print("Usage: python update_repos.py --repos repo1 repo2 ... --files file1 file2 ... [--skip skip1 skip2 ...]")
        sys.exit(1)

    repos_index = sys.argv.index('--repos') + 1
    files_index = sys.argv.index('--files') + 1
    skip_index = sys.argv.index('--skip') + 1 if '--skip' in sys.argv else None

    repo_urls = sys.argv[repos_index:files_index - 1]
    files_to_copy = sys.argv[files_index:skip_index - 1] if skip_index else sys.argv[files_index:]
    skip_items = sys.argv[skip_index:] if skip_index else []

    print(repo_urls, files_to_copy, skip_items)

    if not repo_urls or not files_to_copy:
        print("Both repository URLs and files must be specified.")
        sys.exit(1)

    # Verify if all specified files and folders exist in the current directory
    for item in files_to_copy:
        if not os.path.exists(os.path.join(os.getcwd(), item)):
            print(f"Error: {item} does not exist in the current directory.")
            sys.exit(1)

    # Get the parent directory
    parent_dir = os.path.abspath(os.path.join(os.getcwd(), os.pardir))

    # Get tags from the current HEAD in the working directory
    current_tags = run_command("git tag --points-at HEAD").split('\n')
    cwd = os.getcwd()
    latest_commit_message = get_latest_commit_message()

    for index, repo_url in enumerate(repo_urls):
        print(f"Processing {repo_url}")
        repo_name = f"repo_{index}"
        target_repo_path = os.path.join(parent_dir, repo_name)

        # Clone the repository into the parent directory
        if os.path.exists(target_repo_path):
            shutil.rmtree(target_repo_path, onerror=on_rm_error)
            print(f'delete folder: {target_repo_path}')
        run_command(f"git clone {repo_url} {target_repo_path}")
        print(f'clone folder: {target_repo_path}')
        os.chdir(target_repo_path)

        # Get the current branch name of the target repo
        current_branch = get_current_branch()

        for root, dirs, files in os.walk(target_repo_path):
            # Prune directories
            dirs[:] = [d for d in dirs if os.path.relpath(os.path.join(root, d), target_repo_path) != '.git'
                       and os.path.relpath(os.path.join(root, d), target_repo_path) != '.gitignore']

            for name in dirs + files:
                item_path = os.path.join(root, name)
                relative_path = os.path.relpath(item_path, target_repo_path)
                src_item_path = os.path.join(cwd, relative_path)
                if not os.path.exists(src_item_path) or should_skip(src_item_path, skip_items):
                    run_command(f"git rm -rf {relative_path}")
                    print(f'git rm {relative_path}')
                else:
                    print(f'rm {relative_path}')
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, onerror=on_rm_error)
                    else:
                        os.remove(item_path)

        # Copy specified files and folders to the cloned repository
        os.chdir(cwd)
        for item in files_to_copy:
            if not should_skip(item, skip_items):
                src = os.path.join(os.getcwd(), item)
                dest = os.path.join(target_repo_path, item)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dest)
                    else:
                        shutil.copy2(src, dest)
                except Exception as e:
                    print(f"Error: {src} to {dest} could not be copied.")
                    raise e

        os.chdir(target_repo_path)

        # Add the copied files and folders to the git index
        run_command("git rm -r --cached .")
        run_command("git add .")
        try:
            run_command(f'git commit -m "{latest_commit_message}"')
            # Push the changes and tags to the remote repository
            run_command(f"git push origin {current_branch} --force")
        except:
            print(f"nothing to commit next")

        for tag in current_tags:
            if tag:
                try:
                    run_command(f"git tag -d {tag}")
                except Exception as e:
                    print(f"Error: {tag} could not be deleted.")
                run_command(f'git tag {tag} -m "add {tag}"')
                run_command(f"git push origin {tag} --force")
                print(f'pushed tag {tag}')

    print("Operation completed successfully for all repositories.")


if __name__ == "__main__":
    main()

# python -m ok.update.push_repos --repos https://github.com/ok-oldking/test --files src ok config.py launcher.json launcher.py main.py ok-ww.exe main.py main_debug.py main_gpu.py main_gpu_debug.py assets i18n icon.png requirements.txt
