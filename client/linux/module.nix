{
  config,
  lib,
  pkgs,
  ...
}:

with lib;

let
  cfg = config.services.remoteIntercom;
in
{
  options.services.remoteIntercom = {
    enable = mkEnableOption "remote intercom notification service";

    port = mkOption {
      type = types.port;
      default = 31941;
    };

    openPort = mkEnableOption "opening the UDP firewall port";

    timeout = mkOption {
      type = types.ints.positive;
      default = 10;
    };

    doorbellSound = mkOption {
      type = types.path;
      default = ../resources/doorbell.ogg;
    };

    icon = mkOption {
      type = types.path;
      default = ../resources/door-closed-solid.png;
    };
  };

  config = mkIf cfg.enable {
    systemd.user.services.remote-intercom = {
      description = "Remote Intercom";
      path = [ pkgs.libnotify ];

      environment = {
        DOORBELL_SOUND_PATH = toString cfg.doorbellSound;
        ICON_PATH = toString cfg.icon;
        LISTENING_PORT = toString cfg.port;
        NOTIFICATION_TIMEOUT_S = toString cfg.timeout;
      };

      wantedBy = [ "graphical-session.target" ];
      partOf = [ "graphical-session.target" ];
      after = [ "graphical-session.target" ];

      serviceConfig = {
        ExecStart = "${getExe pkgs.python3} ${./main.py}";
        Restart = "on-failure";
        RestartSec = 5;
      };
    };

    networking.firewall.allowedUDPPorts = optional cfg.openPort cfg.port;
  };
}
