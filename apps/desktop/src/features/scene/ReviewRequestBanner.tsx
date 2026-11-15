import React from "react";
import { Link, useLocation } from "react-router";
import { BellRing, X } from "lucide-react";
import { paths } from "../../app/routes";
import { useUnreviewedCount } from "./sceneQueries";

const onScenePage = (pathname: string) => pathname.startsWith("/create/scene");

/** The review request: a small corner alert like the job alerts. The X closes it; the header badge keeps the count. Not a blocking pop-up. */
export const ReviewRequestBannerView: React.FC<{ count: number; firstRunId: string | null; pathname: string; onDismiss?: () => void }> = ({ count, firstRunId, pathname, onDismiss }) => {
  if (count <= 0 || onScenePage(pathname)) return null;
  return (
    <div
      data-testid="review-alert"
      role="status"
      className="fixed right-6 top-16 z-40 flex w-full max-w-sm items-start gap-3 rounded-xl border border-warn/60 bg-flat/95 p-3.5 text-fg shadow-2xl backdrop-blur-md"
    >
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-warn/20 text-warn"><BellRing size={16} aria-hidden /></span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-xs font-bold">{count === 1 ? "1 picture is waiting for your review" : `${count} pictures are waiting for your review`}</p>
        <Link to={paths.scene(firstRunId ?? undefined)} className="text-[11px] font-semibold text-info hover:underline">Review now</Link>
      </div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} title="Dismiss" aria-label="Dismiss" className="-mr-1 -mt-1 flex h-5 w-5 items-center justify-center rounded text-fg-dim hover:bg-flat hover:text-fg">
          <X size={14} />
        </button>
      )}
    </div>
  );
};

export const ReviewRequestBanner: React.FC = () => {
  const { count, firstRunId } = useUnreviewedCount();
  const { pathname } = useLocation();
  const [dismissedAt, setDismissedAt] = React.useState(0);   // closed at this count; it comes back only when more pictures arrive
  React.useEffect(() => { if (count < dismissedAt) setDismissedAt(count); }, [count, dismissedAt]);   // some were reviewed: later arrivals count as new
  return <ReviewRequestBannerView count={count > dismissedAt ? count : 0} firstRunId={firstRunId} pathname={pathname} onDismiss={() => setDismissedAt(count)} />;
};

/** A small count next to the notification bell. */
export const ReviewBadge: React.FC = () => {
  const { count, firstRunId } = useUnreviewedCount();
  if (count <= 0) return null;
  return (
    <Link
      to={paths.scene(firstRunId ?? undefined)}
      data-testid="review-badge"
      aria-label={`${count} pictures waiting for review`}
      title="Pictures waiting for your review"
      className="rounded-full border border-warn/70 bg-warn/25 px-2 py-0.5 text-xs font-bold text-warn animate-pulse hover:bg-warn/40"
    >
      {count}
    </Link>
  );
};
