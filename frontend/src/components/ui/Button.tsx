import React from "react";
import { cn } from "@/lib/utils/cn";
import { LatticeLoader } from "./LatticeLoader";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg" | "icon";
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "secondary",
      size = "md",
      isLoading = false,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center whitespace-nowrap font-medium rounded-md transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 select-none";

    const variantStyles = {
      primary:
        "bg-primary text-primary-foreground font-semibold hover:bg-primary-hover shadow-sm active:translate-y-px",
      secondary:
        "bg-surface text-foreground hover:bg-surface-hover active:bg-surface-active border border-card-border",
      outline:
        "bg-transparent text-foreground border border-surface-border hover:bg-surface-hover hover:border-zinc-700",
      ghost:
        "bg-transparent text-muted-foreground hover:text-foreground hover:bg-surface",
      destructive:
        "bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20 active:bg-rose-500/30",
    };

    const sizeStyles = {
      sm: "h-8 px-3 text-xs gap-1.5",
      md: "h-9 px-4 text-sm gap-2",
      lg: "h-11 px-6 text-base gap-2.5",
      icon: "h-9 w-9 p-0",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(
          baseStyles,
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...props}
      >
        {isLoading && (
          <LatticeLoader size={16} stepMs={400} className="shrink-0" />
        )}
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";
