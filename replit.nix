{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip

    # System Chromium + the shared libraries a headless browser needs.
    pkgs.chromium
    pkgs.glib
    pkgs.nss
    pkgs.nspr
    pkgs.dbus
    pkgs.atk
    pkgs.at-spi2-atk
    pkgs.at-spi2-core
    pkgs.cups
    pkgs.libdrm
    pkgs.expat
    pkgs.libxkbcommon
    pkgs.mesa
    pkgs.alsa-lib
    pkgs.pango
    pkgs.cairo
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXext
    pkgs.xorg.libXfixes
    pkgs.xorg.libXrandr
    pkgs.xorg.libxcb
    pkgs.fontconfig
    pkgs.freetype
  ];

  env = {
    # Point Playwright at the Nix-provided Chromium (resolves all runtime libs via Nix).
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = "${pkgs.chromium}/bin/chromium";
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
  };
}
