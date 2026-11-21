"""Deterministic TX packet placement on a GNU Radio complex-sample timeline.

This is a timing planner only: it never changes TinyGS tuning or transmits RF.
The SDR integration should gate already-modulated complex samples after GFSK
modulation, before the time-varying Doppler rotator.
"""
from dataclasses import dataclass
from fractions import Fraction
import csv
import argparse


def _to_fraction(value):
    # String conversion avoids common float binary artefacts for decimal ms.
    return Fraction(str(value))


def _samples_for_ms(ms, sample_rate):
    exact = _to_fraction(ms) * sample_rate / 1000
    # nearest sample, with deterministic half-up rounding (nonnegative only)
    return (exact.numerator * 2 + exact.denominator) // (2 * exact.denominator)


@dataclass(frozen=True)
class TxEvent:
    packet_id: int
    start_sample: int
    end_sample: int  # exclusive
    sample_rate: int

    @property
    def start_seconds(self):
        return self.start_sample / self.sample_rate

    @property
    def end_seconds(self):
        return self.end_sample / self.sample_rate


def plan_tx(*, sample_rate: int, period_ms, phase_ms, packet_samples: int,
            count: int):
    """Place count numbered packet waveforms relative to shared virtual t0.

    All intervals are integer samples. 0 <= phase < period and each packet
    must fit before the next. The caller is responsible for creating the IQ
    waveform and for mapping sample 0 to the shared simulation start.
    """
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError('sample_rate must be a positive integer')
    if not isinstance(packet_samples, int) or packet_samples <= 0:
        raise ValueError('packet_samples must be a positive integer')
    if not isinstance(count, int) or count <= 0:
        raise ValueError('count must be a positive integer')
    period_f = _to_fraction(period_ms)
    phase_f = _to_fraction(phase_ms)
    if period_f <= 0 or not 0 <= phase_f < period_f:
        raise ValueError('require period_ms > 0 and 0 <= phase_ms < period_ms')
    period_samples = _samples_for_ms(period_ms, sample_rate)
    phase_samples = _samples_for_ms(phase_ms, sample_rate)
    if period_samples < 1 or phase_samples >= period_samples:
        raise ValueError('timing not representable at this sample rate')
    if packet_samples > period_samples:
        raise ValueError('packet waveform longer than TX period')
    return [TxEvent(i, phase_samples + i * period_samples,
                    phase_samples + i * period_samples + packet_samples,
                    sample_rate) for i in range(count)]


def write_csv(events, destination):
    with open(destination, 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('packet_id', 'start_sample', 'end_sample',
                         'start_seconds', 'end_seconds'))
        for event in events:
            writer.writerow((event.packet_id, event.start_sample,
                             event.end_sample, f'{event.start_seconds:.9f}',
                             f'{event.end_seconds:.9f}'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Create a sample-exact phased-TX schedule (no RF)')
    parser.add_argument('--sample-rate', type=int, required=True)
    parser.add_argument('--period-ms', required=True)
    parser.add_argument('--phase-ms', required=True)
    parser.add_argument('--packet-samples', type=int, required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--csv', required=True)
    args = parser.parse_args(argv)
    events = plan_tx(sample_rate=args.sample_rate, period_ms=args.period_ms,
                     phase_ms=args.phase_ms, packet_samples=args.packet_samples,
                     count=args.count)
    write_csv(events, args.csv)
    print(f'Created {len(events)} packet events in {args.csv}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
