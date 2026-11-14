import React from "react";
import { Link, useLocation } from "react-router";
import { BellRing } from "lucide-react";
import { paths } from "../../app/routes";
import { useUnreviewedCount } from "./sceneQueries";

const onScenePage = (pathname: string) => pathname.startsWith("/create/scene");

/** The review request: strong colour, pulsing like the error bell, stays until the pictures are reviewed or dismissed. Not a blocking pop-up. */
export const ReviewRequestBannerView: React.FC<{ count: number; firstRunId: string | null; pathname: string }> = ({ count, firstRunId, pathname }) => {
  if (count <= 0 || onScenePage(pathname)) return null;
  return (
    <div
      data-testid="review-banner"
      role="status"
      className="mx-4 mb-2 flex items-center gap-3 rounded-xl border border-warn/70 bg-warn/20 px-4 py-2.5 text-sm text-fg animate-pulse"
    >
      <BellRing size={18} className="text-warn" aria-hidden />
      <span className="flex-1 font-medium">
        {count === 1 ? "1 picture is waiting for your review" : `${count} pictures are waiting for your review`}
      </span>
      <Link to={paths.scene(firstRunId ?? undefined)} className="rounded-lg border border-warn/70 bg-warn/30 px-3 py-1 text-sm font-semibold text-fg hover:bg-warn/50">
        Review now
      </Link>
    </div>
  );
};

export const ReviewRequestBanner: React.FC = () => {
  const { count, firstRunId } = useUnreviewedCount();
  const { pathname } = useLocation();
  return <ReviewRequestBannerView count={count} firstRunId={firstRunId} pathname={pathname} />;
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
