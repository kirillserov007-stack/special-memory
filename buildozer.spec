[app]
title = Blocks Stafn
package.name = blocksstafn
package.domain = org.stafn
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,json,atlas,txt
version = 1.3
requirements = python3,kivy
orientation = portrait
fullscreen = 1

# Интернет нужен только для необязательной онлайн-таблицы лидеров.
android.permissions = INTERNET

# Совместимость с современными Android.
android.api = 35
android.minapi = 23
android.ndk = 27c
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
