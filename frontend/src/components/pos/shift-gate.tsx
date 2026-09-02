"use client";

import { Loader2, Wallet } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * A till cannot take money until someone has counted what is already in the
 * drawer. Without an opening float there is nothing to reconcile against at
 * close, which makes the whole cash-handling trail worthless.
 */
export function ShiftGate({
  onOpen,
  isPending,
}: {
  onOpen: (openingFloat: string) => void;
  isPending: boolean;
}) {
  const [openingFloat, setOpeningFloat] = useState("0.00");

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="bg-primary/10 text-primary mb-2 flex size-11 items-center justify-center rounded-xl">
            <Wallet className="size-5" />
          </div>
          <CardTitle>Open your till</CardTitle>
          <CardDescription>
            Count the cash in the drawer and enter it. Closing the shift will
            reconcile against this.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-2">
          <Label htmlFor="opening-float">Opening float</Label>
          <Input
            id="opening-float"
            inputMode="decimal"
            value={openingFloat}
            onChange={(event) => setOpeningFloat(event.target.value)}
            className="numeric h-14 text-center text-2xl"
            autoFocus
          />
        </CardContent>

        <CardFooter className="mt-4">
          <Button
            className="h-12 w-full"
            onClick={() => onOpen(openingFloat || "0")}
            disabled={isPending}
          >
            {isPending && <Loader2 className="size-4 animate-spin" />}
            Start shift
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
