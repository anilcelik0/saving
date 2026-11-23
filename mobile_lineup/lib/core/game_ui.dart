import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import 'theme.dart';

/// Pieces shared by the game screens (Phase 8 "Gündüz" design).

/// Back button, title and an optional trailing widget (lives, streak counter, ...).
class GameHeader extends StatelessWidget {
  const GameHeader({super.key, required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
        child: Row(
          children: [
            CircleIconButton(
              icon: Icons.chevron_left,
              tooltip: 'Geri',
              onPressed: () => context.canPop() ? context.pop() : context.go('/home'),
            ),
            const SizedBox(width: 12),
            Expanded(child: Text(title, style: display(20), maxLines: 1, overflow: TextOverflow.ellipsis)),
            ?trailing,
          ],
        ),
      );
}

/// Filled / empty hearts for the lives left.
class Hearts extends StatelessWidget {
  const Hearts({super.key, required this.lives, this.max = 3});

  final int lives;
  final int max;

  @override
  Widget build(BuildContext context) {
    final total = lives > max ? lives : max;
    return Semantics(
      label: '$total candan $lives can kaldı',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < total; i++)
            Padding(
              padding: const EdgeInsets.only(left: 2),
              // A lost life pops (the only sign of a wrong move on the timeline).
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 450),
                transitionBuilder: (child, animation) => FadeTransition(
                  opacity: animation,
                  child: ScaleTransition(
                    scale: Tween(begin: 1.8, end: 1.0)
                        .animate(CurvedAnimation(parent: animation, curve: Curves.easeOutBack)),
                    child: child,
                  ),
                ),
                child: Icon(
                  i < lives ? Icons.favorite : Icons.favorite_border,
                  key: ValueKey(i < lives),
                  size: 20,
                  color: const Color(0xFFD64545),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// White rounded panel (end of a run, intro boxes).
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(20), this.margin});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) => Container(
        margin: margin,
        padding: padding,
        decoration: BoxDecoration(color: LU.surface, borderRadius: BorderRadius.circular(24), boxShadow: LU.shadow),
        child: child,
      );
}

/// Error text + retry button, centered.
class GameMessage extends StatelessWidget {
  const GameMessage({super.key, required this.text, required this.action, required this.onAction});

  final String text;
  final String action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(padding: const EdgeInsets.all(24), child: Text(text, textAlign: TextAlign.center)),
            FilledButton(onPressed: onAction, child: Text(action)),
          ],
        ),
      );
}
