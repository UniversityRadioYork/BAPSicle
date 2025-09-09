{ pkgs }:
let
  src = pkgs.fetchFromGitHub {
    owner = "UniversityRadioYork";
    repo = "WebStudio";
    rev= "ca4b8f6e45e88914912e63425d061ac8cb7d91c7";
    hash = "sha256-wjQhNZyIqu61h14d6isTWymv9ajYeu/JG5WvKh1pdd8=";
  };
  yarnOfflineCache = pkgs.fetchYarnDeps {
    yarnLock = "${src}/yarn.lock";
    hash = "sha256-AmKui+Sqyipy4/9lcg8vGWfp9lM2+/fHHDzEWoG8fqw=";
  };
in
pkgs.stdenv.mkDerivation {
  name = "baps-presenter";
  inherit src;

  nativeBuildInputs = with pkgs; [
    nodejs
    yarn
    yarn2nix-moretea.fixup_yarn_lock
  ];

  configurePhase = ''
  export HOME=$(mktemp -d)
  '';

  buildPhase = ''
  yarn config --offline set yarn-offline-mirror ${yarnOfflineCache}
  fixup_yarn_lock yarn.lock
  yarn install --offline \
    --frozen-lockfile \
    --ignore-engines \
    --ignore-scripts
  patchShebangs .

  yarn run build-baps
  '';

  installPhase = ''
  mkdir -p $out
  cp -R build/. $out
  '';

  doDist = false;
}
