baps-overlay:

{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.bapsicle;
in

{
  options.services.bapsicle = {
    enable = lib.mkEnableOption "BAPSicle server";
  };

  config = {
    nixpkgs.overlays = [baps-overlay];

    systemd.user.services.bapsicle = lib.mkIf cfg.enable {
      description = "BAPS 3 Server";

      serviceConfig = {
        ExecStart = "${pkgs.lib.makeBinPath pkgs.bapsicle}";
        WorkingDirectory = "%h/.local/state/bapsicle"
        LockPersonality = "yes";
        MemoryDenyWriteExecute = "yes";
        NoNewPrivileges = "yes";
        Restart = "on-failure";
        RestrictNamespaces = "yes";
        SystemCallArchitectures = "native";
        SystemCallFilter = "@system-service";
        TimeoutSec = "13500000000000";
      };

      after = ["pipewire-pulse.socket"];
      wantedBy = ["default.target"];
    };
  };
}
