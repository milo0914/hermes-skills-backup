# Hermes Agent 技能安裝模式

本文檔記錄了在 Hermes Agent 中安裝和管理技能的實戰經驗和最佳實踐。

## 技能來源一覽表

| 來源 | 模式 | 示例 | 信任度 |
|------|------|------|--------|
| **skills.sh** | `skills-sh/<path>` | `skills-sh/anthropics/skills/skill-creator` | ⭐⭐⭐⭐ |
| **Anthropic 官方** | GitHub URL | `https://raw.githubusercontent.com/anthropics/skills/...` | ⭐⭐⭐⭐⭐ |
| **Vercel Labs** | GitHub URL | `https://raw.githubusercontent.com/vercel-labs/skills/...` | ⭐⭐⭐⭐ |
| **superpowers-zh** | GitHub 克隆 | `github.com/jnMetaCode/superpowers-zh` | ⭐⭐⭐⭐ |
| **LobeHub** | `lobehub/<name>` | `lobehub/singer` | ⭐⭐⭐ |
| **ClawHub** | `clawhub/<name>` | `clawhub/1password` | ⭐⭐⭐ |

## 安裝模式

### 模式 1：從 skills.sh 安裝（推薦）

```bash
# 通過 skills.sh 註冊表安裝（自動解析）
hermes skills install skills-sh/anthropics/skills/skill-creator --force

# 先檢查
hermes skills inspect skills-sh/anthropics/skills/skill-creator
```

### 模式 2：從 GitHub URL 直接安裝

```bash
# Anthropic 官方技能
hermes skills install https://raw.githubusercontent.com/anthropics/skills/f458cee31a7577a47ba0c9a101976fa599385174/skills/skill-creator/SKILL.md --force

# Vercel Labs 技能
hermes skills install https://raw.githubusercontent.com/vercel-labs/skills/c99a72b371b5b4da865f5afa87c5a686f3a46766/skills/find-skills/SKILL.md --force
```

**注意：** 必須使用 raw.githubusercontent.com URL，不是 github.com 的 tree/blob URL。

### 模式 3：批量安裝（superpowers-zh 模式）

對於包含多個技能的倉庫：

```bash
# 1. 克隆倉庫
cd /tmp && git clone --depth 1 https://github.com/jnMetaCode/superpowers-zh.git

# 2. 複製到 Hermes 技能目錄
mkdir -p /data/.hermes/skills/superpowers-zh
cp -r /tmp/superpowers-zh/skills/* /data/.hermes/skills/superpowers-zh/

# 3. 驗證安裝
hermes skills list | grep superpowers
```

### 模式 4：單獨安裝技能

```bash
# 對於單個技能文件
for skill in brainstorming executing-plans writing-plans; do
  printf "devops\ny\n" | hermes skills install file:///tmp/superpowers-zh/skills/$skill/SKILL.md --force
done
```

## 安全掃描覆蓋

當安裝技能時，可能會遇到安全掃描警告：

**常見警告：**
- `HIGH exfiltration`: API 密鑰處理、外部 API 調用
- `MEDIUM supply_chain`: `pip install`、`curl` 下載外部腳本
- `MEDIUM execution`: 使用 `subprocess.run`
- `MEDIUM obfuscation`: base64 編碼、atob 解碼

**覆蓋方法：**
```bash
# 信任來源時使用 --force
hermes skills install <skill> --force

# 同時跳过確認提示
echo "y" | hermes skills install <skill> --force
```

## 分類處理

安裝時可能會提示選擇分類：

```bash
# 提供分類的快捷方式
printf "devops\ny\n" | hermes skills install <url>
printf "creative\ny\n" | hermes skills install <url>
printf "research\ny\n" | hermes skills install <url>
```

**常用分類：**
- `devops` - 運維、技能管理、調試
- `creative` - 設計、寫作、音樂
- `research` - 學術、PDF、網頁研究
- `superpowers-zh` - 中文增強技能包

## 技能備份

### 完整備份所有技能

```bash
# 創建備份
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="/tmp/hermes_skills_backup_$timestamp"
mkdir -p "$backup_dir"

# 複製所有技能
cp -r /data/.hermes/skills/* "$backup_dir/"

# 創建壓縮包
tar -czf "${backup_dir}.tar.gz" -C "$(dirname $backup_dir)" "$(basename $backup_dir)"

echo "備份完成：${backup_dir}.tar.gz ($(du -h ${backup_dir}.tar.gz | cut -f1))"
```

### 推送到 GitHub

```bash
# 準備推送
repo_dir="/tmp/hermes-skills-backup"
cp -r /data/.hermes/skills/* "$repo_dir/"
cd "$repo_dir"

# 添加 README
cat > README.md << EOF
# Hermes Skills Backup

備份時間：$(date +%Y-%m-%d)
包含技能數量：$(ls -1 | wc -l) 個

## 還原方式
\`\`\`bash
git clone <repo-url>
cd hermes-skills-backup
cp -r * /data/.hermes/skills/
\`\`\`
EOF

# Git 推送
git init
git config user.name "Hermes Agent"
git config user.email "hermes@nousresearch.com"
git add .
git commit -m "Backup Hermes skills $(date +%Y-%m-%d)"
git remote add origin "https://<TOKEN>@github.com/<USER>/<REPO>.git"
git push -u origin main --force
```

## 疑難排解

### 問題：技能已存在但無法使用

**解決方案：**
```bash
# 檢查技能狀態
hermes skills list | grep <skill-name>

# 重新安裝
hermes skills uninstall <skill-name>
hermes skills install <source> --force
```

### 問題：安裝時卡住或超時

**解決方案：**
```bash
# 使用 --force 跳过確認
hermes skills install <source> --force

# 或提供默認輸入
printf "devops\ny\n" | hermes skills install <url>
```

### 問題：技能文件存在但未啟用

**解決方案：**
```bash
# 檢查技能目錄
ls -la /data/.hermes/skills/<skill-name>/

# 確認 SKILL.md 存在
cat /data/.hermes/skills/<skill-name>/SKILL.md | head -5
```

## 已驗證的來源

### 官方來源
- ✅ `anthropics/skills` - Anthropic 官方技能
- ✅ `vercel-labs/skills` - Vercel Labs 技能
- ✅ `NousResearch/hermes-agent` - Hermes Agent 官方技能

### 社區來源
- ✅ `jnMetaCode/superpowers-zh` - 中文增強技能包（20 個技能）
- ✅ `ComposioHQ/awesome-claude-skills` - 技能集合

## 最佳實踐

1. **優先使用 skills.sh**：自動解析和驗證
2. **檢查來源可信度**：查看 stars、安裝數、作者信譽
3. **備份技能**：定期備份到 GitHub 或本地
4. **分類管理**：使用一致的分類（devops、creative、research）
5. **記錄安裝來源**：在 SKILL.md 中註明來源 URL
6. **測試後再使用**：安裝後驗證技能是否正常工作

## 相關資源

- [Hermes Agent 文檔](https://hermes-agent.nousresearch.com/docs/skills)
- [Skills Hub](https://agentskills.io)
- [skills.sh](https://skills.sh/)
- [superpowers-zh](https://github.com/jnMetaCode/superpowers-zh)
