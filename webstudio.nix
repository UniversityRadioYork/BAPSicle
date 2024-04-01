{ pkgs }:
let
  src = pkgs.fetchFromGitHub {
    owner = "UniversityRadioYork";
    repo = "WebStudio";
    rev= "8b7f59cdc6ed80b525b2dff665308d808a526d97";
    hash = "sha256-I+N/mskX8/gN065SqPxmOn3nrHKPWPcIZygSGbB6GEE=";
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
