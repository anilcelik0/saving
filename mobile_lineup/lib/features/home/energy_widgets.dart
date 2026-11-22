import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../billing/reward_ads.dart';
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
    if (e.unlimited && e.pro) {
      title = 'Enerji: sınırsız · Pro';
      subtitle = e.unlimitedSeconds == null
          ? 'Pro üyeliğin aktif'
          : 'Pro: ${formatWait(e.left(e.unlimitedSeconds!, now))} kaldı';
    } else if (e.unlimited) {
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

/// Shown when a start returns `no_energy`: +1 energy for a rewarded ad (granted by the server) or Pro.
Future<void> showNoEnergyDialog(BuildContext context, WidgetRef ref) async {
  ref.invalidate(homeProvider);
  HomeInfo? home;
  try {
    home = await ref.read(homeProvider.future);
  } catch (_) {
    home = null;
  }
  if (!context.mounted) return;
  final granted = await showDialog<bool>(context: context, builder: (context) => _NoEnergyDialog(home: home));
  if (granted == true && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('+1 enerji kazandın!')));
  }
}

class _NoEnergyDialog extends ConsumerStatefulWidget {
  const _NoEnergyDialog({required this.home});

  final HomeInfo? home;

  @override
  ConsumerState<_NoEnergyDialog> createState() => _NoEnergyDialogState();
}

class _NoEnergyDialogState extends ConsumerState<_NoEnergyDialog> {
  bool _busy = false;
  String? _error;

  Future<void> _watch() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final granted = await ref.read(rewardAdsProvider).watch(rewardEnergy);
      ref.invalidate(homeProvider);
      if (!mounted) return;
      if (granted) {
        Navigator.pop(context, true);
      } else {
        setState(() => _error = 'Reklam bitmeden kapatıldı; enerji verilmedi.');
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final next = widget.home?.energy.nextInSeconds;
    final adsLeft = widget.home?.adsLeftToday;
    final ads = ref.read(rewardAdsProvider);
    final canWatch = !_busy && ads.available && adsLeft != 0;
    return AlertDialog(
      icon: const Icon(Icons.bolt),
      title: const Text('Enerjin bitti'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(next == null ? 'Yeni enerji birazdan gelir.' : 'Bir sonraki enerji ${formatWait(next)} sonra.'),
          const SizedBox(height: 16),
          FilledButton.tonalIcon(
            onPressed: canWatch ? _watch : null,
            icon: _busy
                ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.ondemand_video),
            label: const Text('Reklam izle, +1 enerji'),
          ),
          if (adsLeft != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(adsLeft == 0 ? 'Bugünlük reklam hakkın bitti.' : 'Bugün $adsLeft reklam hakkın var.',
                  textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _busy
                ? null
                : () {
                    Navigator.pop(context);
                    context.push('/home/pro');
                  },
            icon: const Icon(Icons.workspace_premium),
            label: const Text('Pro: sınırsız enerji'),
          ),
        ],
      ),
      actions: [TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Tamam'))],
    );
  }
}
