import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../home/home_data.dart';
import 'reward_ads.dart';

/// "+1 can, devam et" after a lost run (once per run): free for Pro, otherwise for a rewarded ad. The server
/// resumes the run; [onResumed] reloads it.
class ContinueOffer extends ConsumerStatefulWidget {
  const ContinueOffer({super.key, required this.runId, required this.onResumed});

  final String runId;
  final Future<void> Function() onResumed;

  @override
  ConsumerState<ContinueOffer> createState() => _ContinueOfferState();
}

class _ContinueOfferState extends ConsumerState<ContinueOffer> {
  bool _busy = false;

  Future<void> _run(Future<bool> Function() action) async {
    setState(() => _busy = true);
    try {
      if (await action()) {
        await widget.onResumed();
        ref.invalidate(homeProvider);
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Reklam bitmeden kapatıldı; devam hakkı verilmedi.')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(homeProvider).value;
    final pro = home?.pro.active ?? false;
    final adsLeft = home?.adsLeftToday;
    final ads = ref.read(rewardAdsProvider);
    final icon = _busy
        ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
        : Icon(pro ? Icons.workspace_premium : Icons.ondemand_video);
    if (pro) {
      return FilledButton.tonalIcon(
        onPressed: _busy
            ? null
            : () => _run(() async {
                  await ref.read(apiClientProvider).post('lineup/games/runs/${widget.runId}/continue/');
                  return true;
                }),
        icon: icon,
        label: const Text('Devam et (Pro) · +1 can'),
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        FilledButton.tonalIcon(
          onPressed: _busy || !ads.available || adsLeft == 0
              ? null
              : () => _run(() => ads.watch(rewardContinue, ref: widget.runId)),
          icon: icon,
          label: const Text('Reklam izle, devam et · +1 can'),
        ),
        if (adsLeft == 0) Text('Bugünlük reklam hakkın bitti.', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
