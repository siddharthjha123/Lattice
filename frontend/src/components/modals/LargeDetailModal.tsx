"use client";
import React, { useEffect, useRef, useId } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { uiEase } from "@/components/ui/MotionSurface";
export interface LargeDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  headerAction?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}
export function LargeDetailModal({
  isOpen,
  onClose,
  title,
  subtitle,
  headerAction,
  children,
  footer,
  className,
}: LargeDetailModalProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const reduced = useReducedMotion();
  useEffect(() => {
    if (isOpen && !dialog.current?.open) dialog.current?.showModal();
  }, [isOpen]);
  useEffect(() => {
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isOpen]);
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]',
          ),
        ).filter((element) => element.getClientRects().length > 0);
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first && last) {
          event.preventDefault();
          last.focus();
        } else if (
          !event.shiftKey &&
          document.activeElement === last &&
          first
        ) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className="fixed inset-0 m-0 p-4 sm:p-6 w-screen h-screen max-w-none max-h-none bg-transparent text-foreground backdrop:bg-transparent open:flex open:items-center open:justify-center"
    >
      <AnimatePresence onExitComplete={() => dialog.current?.close()}>
        {isOpen && (
          <React.Fragment key="dialog-content">
            <motion.div
              aria-hidden="true"
              onClick={onClose}
              className="absolute inset-0 bg-black/80"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: uiEase }}
            />
            <motion.div
              initial={{
                opacity: 0,
                transform: reduced ? "none" : "translateY(8px) scale(0.97)",
              }}
              animate={{
                opacity: 1,
                transform: reduced ? "none" : "translateY(0px) scale(1)",
              }}
              exit={{
                opacity: 0,
                transform: reduced ? "none" : "translateY(8px) scale(0.97)",
              }}
              transition={{ duration: 0.2, ease: uiEase }}
              className={cn(
                "relative flex flex-col w-[92vw] max-w-[1440px] h-[88vh] max-h-[900px] rounded-xl border border-surface-border bg-card shadow-2xl overflow-hidden",
                className,
              )}
            >
              <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-surface-border shrink-0">
                <div>
                  <h2 id={titleId} className="text-lg font-semibold">
                    {title}
                  </h2>
                  {subtitle && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {subtitle}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {headerAction}
                  <button
                    type="button"
                    onClick={onClose}
                    aria-label="Close modal"
                    className="p-2 rounded-md hover:bg-surface focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {children}
              </div>
              {footer && (
                <div className="px-6 py-4 border-t border-surface-border flex justify-end gap-3">
                  {footer}
                </div>
              )}
            </motion.div>
          </React.Fragment>
        )}
      </AnimatePresence>
    </dialog>
  );
}
