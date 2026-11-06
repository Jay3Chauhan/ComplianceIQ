"use client";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type Props = React.ComponentProps<typeof Button> & { label: string; side?: "top" | "bottom" | "left" | "right" };

/** Icon-only button with a tooltip and an accessible label. */
export function IconButton({ label, side = "top", size = "icon-sm", variant = "ghost", children, ...props }: Props) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button size={size} variant={variant} aria-label={label} {...props}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={side}>{label}</TooltipContent>
    </Tooltip>
  );
}
