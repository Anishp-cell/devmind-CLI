import os
import logging
from git import Repo

logger = logging.getLogger("devmind.git_parser")

def get_git_history(repo_path: str, max_commits: int = 50) -> list[str]:
    """
    Scans the local git history of the project at repo_path.
    Extracts commit messages, authors, dates, and diffs for each commit,
    returning a list of formatted text logs ready for Cognee ingestion.
    """
    history_logs = []
    try:
        # Check if directory has a git repository initialized
        git_dir = os.path.join(repo_path, ".git")
        if not os.path.exists(git_dir):
            logger.warning(f"No git repository found at '{repo_path}'. Skipping git log ingestion.")
            return history_logs

        repo = Repo(repo_path)
        if repo.bare:
            logger.warning(f"Git repository at '{repo_path}' is bare. Skipping git log ingestion.")
            return history_logs

        # Get commits on active branch
        try:
            commits = list(repo.iter_commits(max_count=max_commits))
        except Exception:
            logger.warning("No commits found in the repository (possibly empty). Skipping git history.")
            return history_logs

        logger.info(f"Extracting git history for the last {len(commits)} commits...")

        for commit in commits:
            commit_info = [
                f"Commit Hash: {commit.hexsha}",
                f"Author: {commit.author.name} <{commit.author.email}>",
                f"Date: {commit.authored_datetime.isoformat()}",
                f"Message: {commit.message.strip()}"
            ]

            # Extract list of files modified and the summary diffs
            changed_files = []
            if len(commit.parents) > 0:
                # Diff against parent commit
                parent = commit.parents[0]
                diffs = parent.diff(commit, create_patch=True)
                for d in diffs:
                    file_path = d.b_path if d.b_path else d.a_path
                    changed_files.append(file_path)
                    
                    # Truncate patch to avoid overwhelming token limits
                    patch_text = d.diff.decode("utf-8", errors="ignore") if d.diff else ""
                    if len(patch_text) > 1000:
                        patch_text = patch_text[:1000] + "\n... [diff truncated for token optimization]"
                    
                    commit_info.append(f"\nDiff for {file_path}:\n{patch_text}")
            else:
                # Root commit (first commit has no parent)
                for file_path in commit.stats.files.keys():
                    changed_files.append(file_path)
                commit_info.append(f"\nFiles added in root commit: {', '.join(changed_files)}")

            commit_log = "\n".join(commit_info)
            history_logs.append(commit_log)

        return history_logs

    except Exception as e:
        logger.error(f"Error parsing git history: {e}", exc_info=True)
        return history_logs


def get_changed_files_git_diff(repo_path: str) -> set[str]:
    """
    Returns a set of relative file paths that have been modified, staged, or changed
    in the uncommitted workspace or last git commit.
    Used for instant incremental re-indexing.
    """
    changed_files = set()
    try:
        git_dir = os.path.join(repo_path, ".git")
        if not os.path.exists(git_dir):
            return changed_files

        repo = Repo(repo_path)
        if repo.bare:
            return changed_files

        # 1. Unstaged changes (working tree vs index)
        for item in repo.index.diff(None):
            p = item.b_path or item.a_path
            if p:
                changed_files.add(p.replace("\\", "/"))

        # 2. Staged changes (index vs HEAD)
        try:
            for item in repo.index.diff('HEAD'):
                p = item.b_path or item.a_path
                if p:
                    changed_files.add(p.replace("\\", "/"))
        except Exception:
            pass

        # 3. Untracked files
        for p in repo.untracked_files:
            if p:
                changed_files.add(p.replace("\\", "/"))

        # 4. If no workspace changes found, include files changed in last commit
        if not changed_files and len(repo.heads) > 0:
            try:
                commit = repo.head.commit
                if commit.parents:
                    for item in commit.parents[0].diff(commit):
                        p = item.b_path or item.a_path
                        if p:
                            changed_files.add(p.replace("\\", "/"))
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Git diff detection failed: {e}")

    return changed_files

