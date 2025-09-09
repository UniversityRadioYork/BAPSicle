{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    {
       overlays.default = final: prev: {
        inherit (self.packages.${prev.system}) bapsicle;
      };
      nixosModules.default = import ./nixos.nix (self.overlays.default);
    } // flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        sanic-cors = import ./sanic-cors.nix {
          inherit (pkgs) lib;
          inherit (pkgs.python313Packages) setuptools packaging sanic buildPythonPackage fetchPypi;
        };
        webstudio = import ./webstudio.nix {
          inherit pkgs;
        };
        ui-templates = pkgs.stdenv.mkDerivation {
          name = "baps-ui-templates";
          src = ./ui-templates;
          phases = "installPhase";
          installPhase = ''
          mkdir -p $out
          cp -R $src/. $out
          '';
        };
        ui-static = pkgs.stdenv.mkDerivation {
          name = "baps-ui-static";
          src = ./ui-static;
          phases = "installPhase";
          installPhase = ''
          mkdir -p $out
          cp -R $src/. $out
          '';
        };
        dependencies = ps: with ps; [
          setuptools
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
        bapsicle = pkgs.python313Packages.buildPythonApplication {
          pname = "bapsicle";
          inherit version;
          doCheck = false;
          build-system = with pkgs.python313Packages; [
            poetry-core
          ];
          dependencies = dependencies pkgs.python313Packages;
          pyproject = true;
          src = ./.;
          patches = [
            ./patches/0-setup.py-fixes.patch
            (pkgs.replaceVars ./patches/1-presenter-build-path.patch {
              baps_presenter = "${webstudio}";
              ui_static = "${ui-static}";
              ui_templates = "${ui-templates}";
            })
            ./patches/2-not-beta.patch
          ];
        };
      in
    {
      packages = rec {
        default = bapsicle;

        inherit bapsicle webstudio;
      };

      devShells.default = pkgs.mkShell {
        nativeBuildInputs = with pkgs; [
          (python311.withPackages dependencies)
          nodejs_20
          yarn
          ffmpeg_6-full
          poetry
        ];
      };
    });
}
