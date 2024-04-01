{
  inputs = {
    nixpkgs.url = github:NixOS/nixpkgs/nixpkgs-unstable;
    flake-utils.url = github:numtide/flake-utils;
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        sanic-cors = import ./sanic-cors.nix {
          inherit (pkgs) lib;
          inherit (pkgs.python311Packages) setuptools packaging sanic buildPythonPackage fetchPypi;
        };
        webstudio = import ./webstudio.nix {
          inherit pkgs;
        };
        dependencies = ps: with ps; [
          setuptools
          wheel
          sanic
          sanic-cors
          pygame
          syncer
          aiohttp
          mutagen
          sounddevice
          setproctitle
          pyttsx3
          websockets
          pyserial
          requests
          jinja2
          pydub
          psutil
        ];
        version = self.shortRev or self.dirtyShortRev or "dirty-inputs";
      in
    {
      packages = rec {
        default = pkgs.python311Packages.buildPythonApplication {
          pname = "bapsicle";
          inherit version;
          doCheck = false;
          propagatedBuildInputs = dependencies pkgs.python311Packages;
          src = ./.;
          patches = [
            ./patches/0-setup.py-fixes.patch
            (pkgs.substituteAll {
              src = ./patches/1-presenter-build-path.patch;
              baps_presenter = "${webstudio}";
            })
          ];
        };

        inherit webstudio;
      };

      devShells.default = pkgs.mkShell {
        nativeBuildInputs = with pkgs; [
          (python311.withPackages dependencies)
          nodejs_20
          yarn
          ffmpeg_6-full
        ];
      };
    });
}
