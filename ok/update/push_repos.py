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


def main():
    if '--repos' not in sys.argv or '--files' not in sys.argv:
        print("Usage: python update_repos.py --repos repo1 repo2 ... --files file1 file2 ...")
        sys.exit(1)

    repos_index = sys.argv.index('--repos') + 1
    files_index = sys.argv.index('--files') + 1

    repo_urls = sys.argv[repos_index:files_index - 1]
    files_to_copy = sys.argv[files_index:]

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
    for repo_url in repo_urls:
        repo_name = os.path.basename(repo_url).replace('.git', '')
        target_repo_path = os.path.join(parent_dir, repo_name)

        # Clone the repository into the parent directory
        if os.path.exists(target_repo_path):
            shutil.rmtree(target_repo_path, onerror=on_rm_error)
        run_command(f"git clone {repo_url} {target_repo_path}")
        os.chdir(target_repo_path)

        # Get the current branch name of the target repo
        current_branch = get_current_branch()

        # Delete files and folders in the target repo if they don't exist in the source
        for item in os.listdir(target_repo_path):
            if item != '.git' and item != '.gitignore':
                target_item_path = os.path.join(target_repo_path, item)
                src_item_path = os.path.join(cwd, item)
                if not os.path.exists(src_item_path):
                    run_command(f"git rm -rf {item}")
                else:
                    if os.path.isdir(target_item_path):
                        shutil.rmtree(target_item_path, onerror=on_rm_error)
                    else:
                        os.remove(target_item_path)

        # Copy specified files and folders to the cloned repository
        os.chdir(cwd)
        for item in files_to_copy:
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
        run_command("git add .")
        try:
            run_command(f'git commit -m "{latest_commit_message}"')
        except Exception as e:
            print(f"continue")
            continue
        # Push the changes and tags to the remote repository
        run_command(f"git push origin {current_branch} --force")
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
