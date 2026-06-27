#!/usr/bin/env python3
"""Kaggle API 認證快速設置腳本

用法：
  python3 setup_kaggle_auth.py --token "KGAT_xxxxx"       # 使用環境變數方式（推薦）
  python3 setup_kaggle_auth.py --username "user" --key "key"  # 使用 kaggle.json 方式
  python3 setup_kaggle_auth.py --verify                    # 驗證現有認證
  python3 setup_kaggle_auth.py --clean                     # 清除所有認證
"""

import os
import sys
import json
import argparse
import stat

KAGGLE_DIR = os.path.expanduser("~/.kaggle")
KAGGLE_JSON = os.path.join(KAGGLE_DIR, "kaggle.json")


def setup_env_token(token: str):
    """設定 KAGGLE_API_TOKEN 環境變數（寫入 .bashrc 或 .profile）"""
    shell_rc = os.path.expanduser("~/.bashrc")
    # 移除舊的 KAGGLE_API_TOKEN 設定
    lines = []
    if os.path.exists(shell_rc):
        with open(shell_rc, "r") as f:
            lines = f.readlines()
    lines = [l for l in lines if not l.strip().startswith("export KAGGLE_API_TOKEN=")]
    lines.append(f'export KAGGLE_API_TOKEN="{token}"\n')
    with open(shell_rc, "w") as f:
        f.writelines(lines)
    # 當前 session 也設定
    os.environ["KAGGLE_API_TOKEN"] = token
    print(f"✅ KAGGLE_API_TOKEN 已寫入 {shell_rc}")


def setup_kaggle_json(username: str, key: str):
    """建立 ~/.kaggle/kaggle.json"""
    os.makedirs(KAGGLE_DIR, exist_ok=True)
    data = {"username": username, "key": key}
    with open(KAGGLE_JSON, "w") as f:
        json.dump(data, f)
    os.chmod(KAGGLE_JSON, stat.S_IRUSR | stat.S_IWUSR)  # 600
    print(f"✅ kaggle.json 已建立: {KAGGLE_JSON} (chmod 600)")


def verify_auth():
    """驗證認證是否正常"""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        kernels = api.kernels_list(mine=True, page_size=3)
        if kernels:
            print("✅ 認證成功！你的 notebooks：")
            for k in kernels:
                print(f"   - {k.ref}: {k.title}")
        else:
            print("✅ 認證成功（尚無 notebooks）")
        return True
    except Exception as e:
        print(f"❌ 認證失敗: {e}")
        return False


def clean_auth():
    """清除所有認證檔案"""
    import shutil
    if os.path.exists(KAGGLE_DIR):
        shutil.rmtree(KAGGLE_DIR)
        print(f"✅ 已清除 {KAGGLE_DIR}")
    # 清除 .bashrc 中的 KAGGLE_API_TOKEN
    shell_rc = os.path.expanduser("~/.bashrc")
    if os.path.exists(shell_rc):
        with open(shell_rc, "r") as f:
            lines = f.readlines()
        lines = [l for l in lines if not l.strip().startswith("export KAGGLE_API_TOKEN=")]
        with open(shell_rc, "w") as f:
            f.writelines(lines)
        print(f"✅ 已從 {shell_rc} 移除 KAGGLE_API_TOKEN")
    if "KAGGLE_API_TOKEN" in os.environ:
        del os.environ["KAGGLE_API_TOKEN"]
    print("✅ 所有認證已清除")


def main():
    parser = argparse.ArgumentParser(description="Kaggle API 認證設置")
    parser.add_argument("--token", help="KAGGLE_API_TOKEN (KGAT_ 格式)")
    parser.add_argument("--username", help="Kaggle 用戶名（kaggle.json 方式）")
    parser.add_argument("--key", help="Kaggle API key（kaggle.json 方式）")
    parser.add_argument("--verify", action="store_true", help="驗證現有認證")
    parser.add_argument("--clean", action="store_true", help="清除所有認證")
    args = parser.parse_args()

    if args.verify:
        verify_auth()
    elif args.clean:
        clean_auth()
    elif args.token:
        setup_env_token(args.token)
        verify_auth()
    elif args.username and args.key:
        setup_kaggle_json(args.username, args.key)
        verify_auth()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
