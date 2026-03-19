# 运行说明（实测版）

## 一键全链路测试

```bash
cd /root/.openclaw/workspace/projects/ths-trend-eod-strategy
python3 run_fullchain_test.py --date $(date +%F)
```

## 下午自动跑入口

```bash
cd /root/.openclaw/workspace/projects/ths-trend-eod-strategy
./run_afternoon_live.sh
```

## 输出文件

- `tail_candidates_YYYY-MM-DD.json`
- `tail_candidates_YYYY-MM-DD.md`
- `fullchain_test_YYYY-MM-DD.json`
