import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import 'home_data.dart';

/// "12:05", "1 sa 15 dk", "2 gün"
String formatWait(int seconds) {
  if (seconds >= 2 * 86400) return '${seconds ~/ 86400} gün';
  if (seconds >= 3600) return '${seconds ~/ 3600} sa ${(seconds % 3600) ~/ 60} dk';
  return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
}

/// Energy line on the home screen; counts down every second and refetches when a point arrives.
class EnergyBadge extends ConsumerStatefulWidget {
  const EnergyBadge({super.key, required this.energy});

  final EnergyInfo energy;

  @override
  ConsumerState<EnergyBadge> createState() => _EnergyBadgeState();
}

class _EnergyBadgeState extends ConsumerState<EnergyBadge> {
  Timer? _timer;
  bool _refreshing = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  @override
  void didUpdateWidget(EnergyBadge oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.energy, widget.energy)) _refreshing = false;
  }

  void _tick() {
    final next = widget.energy.nextInSeconds;
    if (!widget.energy.unlimited && next != null && widget.energy.left(next, DateTime.now()) == 0 && !_refreshing) {
      _refreshing = true;
      ref.invalidate(homeProvider);
    }
    setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final e = widget.energy;
    final now = DateTime.now();
    final theme = Theme.of(context);
    final String title;
    final String subtitle;
    if (e.unlimited) {
      title = 'Enerji: sınırsız';
      subtitle = 'Yeni oyunculara özel · ${formatWait(e.left(e.unlimitedSeconds ?? 0, now))} kaldı';
    } else {
      title = 'Enerji: ${e.current}/${e.max}';
      subtitle = e.nextInSeconds == null
          ? 'Dolu · her tur ${e.cost} enerji'
          : '+1 enerji ${formatWait(e.left(e.nextInSeconds!, now))} sonra · '
              'dolu: ${formatWait(e.left(e.fullInSeconds!, now))}';
    }
    return Card(
      child: ListTile(
        leading: Icon(Icons.bolt, color: theme.colorScheme.primary),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: e.unlimited
            ? null
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < e.max; i++)
                    Icon(Icons.bolt, size: 18, color: i < e.current ? Colors.amber.shade700 : theme.disabledColor),
                ],
              ),
      ),
    );
  }
}

/// Shown when a start returns `no_energy`. Rewarded ad and Pro come in Phase 5.
Future<void> showNoEnergyDialog(BuildContext context, WidgetRef ref) async {
  ref.invalidate(homeProvider);
  HomeInfo? home;
  try {
    home = await ref.read(homeProvider.future);
  } catch (_) {
    home = null;
  }
  if (!context.mounted) return;
  final next = home?.energy.nextInSeconds;
  await showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      icon: const Icon(Icons.bolt),
      title: const Text('Enerjin bitti'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(next == null ? 'Yeni enerji birazdan gelir.' : 'Bir sonraki enerji ${formatWait(next)} sonra.'),
          const SizedBox(height: 16),
          const OutlinedButton(onPressed: null, child: Text('Reklam izle, +1 enerji (yakında)')),
          const SizedBox(height: 8),
          const OutlinedButton(onPressed: null, child: Text('Pro: sınırsız enerji (yakında)')),
        ],
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Tamam'))],
    ),
  );
}
