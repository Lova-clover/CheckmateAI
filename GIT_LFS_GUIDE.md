# GitHub에 CheckmateAI 업로드하기

## 1. Git LFS 설정 (대용량 파일 처리)

puzzles.db 파일은 935MB로 GitHub 파일 크기 제한(100MB)을 초과하므로 Git LFS(Large File Storage)를 사용해야 합니다.

### Git LFS 설치 확인
```powershell
git lfs version
# 출력: git-lfs/3.x.x
```

### Git LFS 활성화 (이미 완료됨)
```powershell
git lfs install
git lfs track "*.db"
```

이 명령은 `.gitattributes` 파일을 생성하며, 다음 내용이 포함됩니다:
```
*.db filter=lfs diff=lfs merge=lfs -text
```

## 2. Git 저장소 초기화 및 커밋

### 파일 추가
```powershell
# .gitattributes 추가 (LFS 설정 파일)
git add .gitattributes

# 대용량 파일 추가 (LFS로 자동 처리됨)
git add puzzles.db

# 나머지 모든 파일 추가
git add .

# 커밋
git commit -m "feat: Add complete chess application with 5M+ puzzles"
```

## 3. GitHub 저장소 생성 및 업로드

### GitHub에서 새 저장소 생성
1. https://github.com/new 접속
2. Repository name: `CheckmateAI` (또는 원하는 이름)
3. Description: `Premium local chess application with Stockfish AI and 5M+ puzzles`
4. Public 또는 Private 선택
5. **DO NOT** initialize with README (이미 있음)
6. Create repository 클릭

### 원격 저장소 연결 및 푸시
```powershell
# GitHub 저장소 URL로 변경 (your-username을 본인 계정으로 변경)
git remote add origin https://github.com/your-username/CheckmateAI.git

# 메인 브랜치로 푸시 (Git LFS가 자동으로 대용량 파일 처리)
git branch -M main
git push -u origin main
```

## 4. Git LFS 대역폭 제한 안내

### GitHub Free 계정
- **저장소당 LFS 용량**: 1GB 무료
- **월 대역폭**: 1GB 무료
- puzzles.db (935MB) 업로드 시 약 935MB 사용

### 용량 초과 시 옵션
1. **Git LFS 대역폭 팩 구매**: $5/월당 50GB
2. **GitHub Pro**: $4/월, 2GB 저장소 + 10GB 대역폭
3. **대안 방법**: puzzles.db를 Git에서 제외하고 README에 다운로드 링크 안내

## 5. puzzles.db를 Git에서 제외하는 방법 (대안)

만약 Git LFS를 사용하지 않으려면:

### .gitignore에 추가
```bash
echo "puzzles.db" >> .gitignore
git rm --cached puzzles.db
git commit -m "Remove puzzles.db from Git tracking"
```

### README.md에 다운로드 안내 추가
```markdown
## 퍼즐 데이터베이스 다운로드

이 프로젝트는 Lichess의 516만개 퍼즐 데이터베이스를 사용합니다.

1. [Lichess Puzzle Database](https://database.lichess.org/#puzzles) 다운로드
2. `puzzles.db` 파일을 프로젝트 루트에 저장
3. 서버 재시작

또는 Google Drive/Dropbox 링크 제공
```

## 6. 추천 방법

**Git LFS 사용 (현재 설정)**을 권장합니다:
- ✅ 사용자가 `git clone`만으로 모든 파일 받기 가능
- ✅ 버전 관리 편리
- ✅ 설정 간단
- ⚠️ GitHub Free 계정은 1GB 제한 주의

## 7. 확인 사항

### LFS 파일 확인
```powershell
git lfs ls-files
# 출력: puzzles.db
```

### 저장소 크기 확인
```powershell
git count-objects -vH
```

### GitHub에서 LFS 사용량 확인
Settings → Billing → Git LFS Data

## 8. 클론 시 주의사항

다른 사용자가 저장소를 클론할 때:

```powershell
# Git LFS가 설치되어 있어야 함
git lfs install

# 클론 (LFS 파일 자동 다운로드)
git clone https://github.com/your-username/CheckmateAI.git

# 만약 LFS 파일이 다운로드되지 않았다면
cd CheckmateAI
git lfs pull
```

## 9. 업로드 진행 상황

Git LFS 파일 업로드는 시간이 걸릴 수 있습니다 (935MB):
- 업로드 속도: 인터넷 속도에 따라 다름
- 평균 10Mbps: 약 12-15분 소요
- 업로드 중 중단하지 마세요!

```powershell
# 업로드 진행 상황 확인
git push -u origin main --progress
```

## 10. 완료!

업로드 완료 후:
1. https://github.com/your-username/CheckmateAI 접속
2. puzzles.db 파일 확인 (Stored with Git LFS 표시)
3. README.md에 저장소 링크 추가
4. GitHub 저장소 설정 → About → Add description, topics

---

**중요**: 
- `.gitattributes` 파일은 반드시 커밋되어야 합니다
- `puzzles.db` 파일은 Git LFS로 자동 처리됩니다
- GitHub Free 계정은 LFS 1GB 제한이 있습니다
