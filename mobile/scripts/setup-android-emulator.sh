#!/usr/bin/env bash
# Android emulator for testing the app on the PC, without Android Studio.
#
# Installs JDK 17, Node 24, the Android SDK command-line tools, the emulator and an
# Android 15 (API 35) virtual phone under $ROOT. Default: /goinfre/$USER/android-dev,
# the big local disk on 42 machines (the home quota is too small: ~10 GB needed).
# Every cache (Gradle, npm, AVDs) goes there too. Safe to rerun, e.g. after a wipe.
#
#   bash mobile/scripts/setup-android-emulator.sh
#   source /goinfre/$USER/android-dev/env.sh     # in each new terminal
#
# Versions follow the React Native 0.88 environment guide (JDK 17, platform 35,
# build-tools 36.0.0); downloads are checked against their published checksums.
set -euo pipefail

ROOT="${ROOT:-/goinfre/$USER/android-dev}"
AVD_NAME="${AVD_NAME:-musicroom}"
NODE_VERSION=v24.22.0
JDK_URL="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.21%2B9/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21_9.tar.gz"
TOOLS_ZIP=commandlinetools-linux-16111833_latest.zip
TOOLS_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60
SYSTEM_IMAGE="system-images;android-35;google_apis;x86_64"

mkdir -p "$ROOT/downloads"
cd "$ROOT/downloads"

# --- JDK 17 (sdkmanager and Gradle need it) ---------------------------------------
if [ ! -x "$ROOT/jdk/bin/java" ]; then
  echo "==> JDK 17"
  jdk_file=$(basename "${JDK_URL//%2B/+}")
  curl -fsSL -o "$jdk_file" "$JDK_URL"
  curl -fsSL -o "$jdk_file.sha256.txt" "$JDK_URL.sha256.txt"
  sha256sum -c "$jdk_file.sha256.txt"
  mkdir -p "$ROOT/jdk"
  tar -xzf "$jdk_file" -C "$ROOT/jdk" --strip-components=1
fi

# --- Node 24 (the system Node is too old for Expo) ---------------------------------
if [ ! -x "$ROOT/node/bin/node" ]; then
  echo "==> Node $NODE_VERSION"
  node_file="node-$NODE_VERSION-linux-x64.tar.xz"
  curl -fsSL -o "$node_file" "https://nodejs.org/dist/$NODE_VERSION/$node_file"
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt" | grep " $node_file\$" | sha256sum -c
  mkdir -p "$ROOT/node"
  tar -xJf "$node_file" -C "$ROOT/node" --strip-components=1
fi

# --- Android command-line tools ------------------------------------------------------
if [ ! -x "$ROOT/sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
  echo "==> Android command-line tools"
  curl -fsSL -o "$TOOLS_ZIP" "https://dl.google.com/android/repository/$TOOLS_ZIP"
  echo "$TOOLS_SHA1  $TOOLS_ZIP" | sha1sum -c
  rm -rf "$ROOT/sdk/cmdline-tools"
  mkdir -p "$ROOT/sdk/cmdline-tools"
  unzip -q "$TOOLS_ZIP" -d "$ROOT/sdk/cmdline-tools"
  mv "$ROOT/sdk/cmdline-tools/cmdline-tools" "$ROOT/sdk/cmdline-tools/latest"
fi

# --- Environment (sourced by you in each terminal) -------------------------------------
cat > "$ROOT/env.sh" <<EOF
# source $ROOT/env.sh
export JAVA_HOME="$ROOT/jdk"
export ANDROID_HOME="$ROOT/sdk"
export ANDROID_SDK_ROOT="$ROOT/sdk"
export ANDROID_USER_HOME="$ROOT/.android"
export ANDROID_AVD_HOME="$ROOT/.android/avd"
export GRADLE_USER_HOME="$ROOT/gradle"
export npm_config_cache="$ROOT/npm-cache"
export PATH="$ROOT/node/bin:$ROOT/jdk/bin:$ROOT/sdk/cmdline-tools/latest/bin:$ROOT/sdk/platform-tools:$ROOT/sdk/emulator:\$PATH"
EOF
# shellcheck disable=SC1091
source "$ROOT/env.sh"

# --- SDK packages + virtual phone ---------------------------------------------------------
echo "==> Android SDK packages (the system image is ~1.5 GB)"
# cmdline-tools 23 replaced sdkmanager with the `android` CLI (packages use slashes,
# licenses no longer need a separate step). --no-metrics: no usage data sent to Google.
android --no-metrics sdk install platform-tools emulator platforms/android-35 build-tools/36.0.0 \
  "${SYSTEM_IMAGE//;//}"

if ! avdmanager list avd -c | grep -qx "$AVD_NAME"; then
  echo "==> Virtual phone '$AVD_NAME'"
  device=$(avdmanager list device -c | grep -m1 -E '^pixel_[0-9]+$' || echo pixel)
  echo no | avdmanager create avd -n "$AVD_NAME" -k "$SYSTEM_IMAGE" -d "$device"
fi

cat <<EOF

Done. In each new terminal:
  source $ROOT/env.sh

Start the virtual phone:     emulator -avd $AVD_NAME &
Run the app (Expo Go):       cd mobile && npm install && npx expo start --android
In the app's Server settings use http://10.0.2.2:8000 (the emulator's name for this PC).
EOF
