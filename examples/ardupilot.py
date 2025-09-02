import multicosim as mcs
import multicosim.ardupilot as ap


def main():
    sim = mcs.ArduPilot(ap.GazeboOptions(), ap.FirmwareOptions())
    sys = sim.start()

    while True:
        try:
            pass
        except KeyboardInterrupt:
            break

    sys.stop()


if __name__ == "__main__":
    main()
