{
  description = "Development shell for the document rectifier";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = function:
        nixpkgs.lib.genAttrs systems (system:
          function (import nixpkgs { inherit system; }));
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.python313
            pkgs.uv
            pkgs.mesa
            pkgs.libglvnd
            pkgs.glib
            pkgs.pkg-config
            pkgs.xorg.libX11
            pkgs.xorg.libXext
            pkgs.xorg.libSM
            pkgs.xorg.libICE
            pkgs.python313Packages.opencv4
          ];

          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.mesa
            pkgs.libglvnd
            pkgs.glib
            pkgs.xorg.libX11
            pkgs.xorg.libXext
            pkgs.xorg.libSM
            pkgs.xorg.libICE
            pkgs.stdenv.cc.cc
          ];

          shellHook = ''
            export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
            export PATH="$PWD/bin:$PATH"

            if [ ! -f .venv/bin/activate ]; then
              echo "Bootstrapping Python environment with uv sync..."
              uv sync
            fi

            . .venv/bin/activate
            echo "DocumentRectifier dev shell ready. Run: run-document-rectifier"
          '';
        };
      });
    };
}