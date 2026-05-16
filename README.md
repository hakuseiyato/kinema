# kinema

Blender 5.x 向けの **カメラ + 独自マルチトラックタイムライン**アドオン。
旧 [cineflow](spike0/../) の機能を吸収しつつ、Premiere 風のショット編集 UI と直感的なカメラ操作を提供する後継。

> 設計プラン v7: `C:/Users/brain/.claude/plans/blender-cineflow-c-work-yato-blender-scr-foamy-bengio.md`

## 状態

**alpha1**（リポ骨格 + ランタイム移植 + Cameras タブ）。

| フェーズ | 状態 |
|---|---|
| spike0 | ✅ 完了（[docs/spike0_findings.md](docs/spike0_findings.md)）8/8 OK |
| **alpha1** | ✅ 実装完了、動作確認待ち |
| alpha2: Pose タブ | 未着手 |
| beta1+: 独自タイムライン | 未着手 |

## ディレクトリ

```
kinema/
├── src/kinema/               # アドオン本体（Junction の張り元）
│   ├── __init__.py
│   ├── blender_manifest.toml
│   ├── preferences.py
│   ├── config/ data/ ops/ ui/ runtime/ utils/ importers/
├── spike0/                   # Blender 5.x API 検証アドオン（完了済み）
├── scripts/                  # dev_install / dev_uninstall
├── docs/                     # spike0_findings.md など
└── tests/                    # 純粋ロジックの pytest
```

## インストール（dev install）

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_install.ps1
# 特定バージョン: .\dev_install.ps1 -BlenderVersion "5.0"
```

`%APPDATA%\Blender Foundation\Blender\<最新>\extensions\user_default\kinema` に Junction が張られる。バージョン自動検出は `config\userpref.blend` の更新日時で「現役」を判定。

## alpha1 の動作確認

詳細手順は [docs/alpha1_smoke_test.md](docs/alpha1_smoke_test.md) を参照。要点：

1. Blender 5.0 を起動 → Preferences > Add-ons で "Kinema" を有効化
2. **cineflow が enabled なら警告**が出るので、Settings バナーから "Disable cineflow & enable kinema handlers" を実行
3. Properties > Scene > Kinema パネルが表示される
4. **Create Kinema Workspace** ボタンで `Kinema` タブが追加される（普段の Layout は触らない）
5. シーンに `Kinema_Presets` コレクションを作り、その中に Camera を含むサブコレクションを置く
6. **Scan Presets** → プリセット一覧が出る
7. プリセットを選択 → **Load Selected Preset** → Instance として複製される
8. Instance の Follow Target / LookAt Target / Noise を設定 → 再生で追従挙動を確認

## テスト

```powershell
cd C:\Work\Yato\Claude\kinema
python tests\test_naming.py
python tests\test_tags.py
python tests\test_damping.py
```

純粋ロジック（bpy 非依存）のみ。UI / Modal / Operator は手動 smoke test で。

## ライセンス

GPL-3.0-or-later
