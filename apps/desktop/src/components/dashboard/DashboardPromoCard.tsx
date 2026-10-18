import React from "react";
import { Sparkles, ArrowRight } from "lucide-react";

interface DashboardPromoCardProps {
  onAction: () => void;
}

export const DashboardPromoCard: React.FC<DashboardPromoCardProps> = ({ onAction }) => {
  return (
    <div className="bg-gradient-to-br from-[#1c1d42] via-[#151733] to-[#101224] border border-[#37326b] rounded-xl p-3.5 relative overflow-hidden shadow-lg select-none group">
      {/* Background ambient glow */}
      <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-indigo-500/15 rounded-full blur-xl pointer-events-none" />

      <div className="flex items-start gap-2 mb-2">
        <Sparkles className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
        <h4 className="text-xs font-bold text-white tracking-tight leading-snug">
          Ready to create something amazing?
        </h4>
      </div>

      <p className="text-[11px] text-zinc-300 leading-relaxed pr-6">
        Import a new manga project and let AI handle the rest.
      </p>

      <div className="flex justify-end mt-2">
        <button
          onClick={onAction}
          className="w-7 h-7 rounded-full bg-[#4338ca] hover:bg-indigo-500 text-white flex items-center justify-center transition-all shadow-md shadow-indigo-600/40 group-hover:scale-105"
          title="Create New Project"
        >
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
