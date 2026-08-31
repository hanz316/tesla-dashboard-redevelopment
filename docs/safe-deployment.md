# 安全部署与回滚方案

## 1. 推荐方案：ADB `/tmp` 临时运行

这是当前唯一推荐的首轮部署路径。FlyThings 官方 IDE 的 `LaunchOverAdb` 源码证明其调试流程是：

1. 将 `EasyUI.cfg`、`libzkgui.so`、FTU/资源推送到指定目录。
2. 对临时模式使用 `/tmp`。
3. 执行 `sync`。
4. 执行 `setprop ctl.restart zkswe`。
5. 不制作、不安装 `update.img`。
6. 设备断电后恢复原应用。

本项目进一步缩小写入范围：

```text
/tmp/EasyUI.cfg
/tmp/tesla-dashboard-mvp/lib/libzkgui.so
```

UI、字体、翻译和图片继续从原只读 `/res` 加载，不复制、不覆盖原文件。

## 2. 首次上机顺序

必须依次执行：

```bash
bash scripts/probe_device_readonly.sh
bash scripts/backup_device_readonly.sh DEVICE_SERIAL
bash scripts/deploy_temporary_adb.sh --temporary DEVICE_SERIAL
```

首次部署前还应人工核对：

- `getprop ro.product.model` / `ro.hardware`
- `uname -m` 为 ARMv7
- `/tmp` 为 tmpfs
- `/res` 为只读或可完整备份
- 实机存在 `/dev/ttyS5`
- 实机 `libstdc++.so.6` 支持 `CXXABI_1.3.9`
- 原 `libeasyui.so` 等 ABI 与 SDK 版本兼容

脚本会拒绝非 ARMv7 或未授权设备；部署需要显式参数 `--temporary` 和 exact ADB serial。

## 3. 回滚

首选回滚：仪表断电重启。`/tmp` 被清空，`zkswe` 回到 `/res/etc/EasyUI.cfg` 与 `/res/lib/libzkgui.so`。

如果仪表仍在线，也可以先删除这两个临时路径再重启 `zkswe`；但首次验证优先使用断电恢复，减少额外命令。

## 4. 当前禁止

- 不把新 `libzkgui.so` 写入 `/res`
- 不 remount rootfs/res 为读写
- 不运行 `zkautoupgrade`
- 不生成或安装持久化 `update.img`
- 不使用 `fastboot`、FEL、U-Boot 或分区写入
- 不发送 MCU/车辆控制 command

持久化 OTA 只有在完整备份、恢复包、实机临时运行稳定和协议验证完成后才进入设计。
