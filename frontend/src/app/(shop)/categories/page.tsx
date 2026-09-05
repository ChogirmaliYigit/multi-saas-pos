"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MoreHorizontal, Plus, Tags, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Category } from "@/lib/api/pos-types";
import { categoriesApi, productsApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { Permission } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

/** The POS grid tiles are coloured from these, so the swatch is the point. */
const SWATCHES = [
  "#0f766e",
  "#1d4ed8",
  "#7c3aed",
  "#be123c",
  "#c2410c",
  "#a16207",
  "#15803d",
  "#334155",
];

export default function CategoriesPage() {
  const canManage = useAuthStore((s) =>
    s.permissions.has(Permission.CATEGORY_MANAGE),
  );
  const [editing, setEditing] = useState<Category | null>(null);
  const [creating, setCreating] = useState(false);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => categoriesApi.list(),
  });

  // Product counts come from the catalog, one page per category, so a
  // category is never deleted without the owner seeing what is inside it.
  const products = useQuery({
    queryKey: ["products", "for-categories"],
    queryFn: () => productsApi.list({ page: 1, size: 200 }),
  });

  const countFor = (categoryId: string) =>
    (products.data?.items ?? []).filter((p) => p.category_id === categoryId).length;

  const items = categories.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Categories"
        description="Organise the catalog and the POS grid."
        actions={
          canManage && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Add category
            </Button>
          )
        }
      />

      {categories.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-14 text-center">
          <Tags className="text-muted-foreground size-8" />
          <div>
            <p className="font-medium">No categories yet</p>
            <p className="text-muted-foreground text-sm">
              Categories become the tiles on the terminal&apos;s product grid.
            </p>
          </div>
          {canManage && (
            <Button variant="outline" onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Add the first one
            </Button>
          )}
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((category) => (
            <CategoryCard
              key={category.id}
              category={category}
              productCount={countFor(category.id)}
              canManage={canManage}
              onEdit={() => setEditing(category)}
            />
          ))}
        </div>
      )}

      <CategoryDialog
        open={creating || editing !== null}
        category={editing}
        onOpenChange={(open) => {
          if (!open) {
            setCreating(false);
            setEditing(null);
          }
        }}
      />
    </div>
  );
}

function CategoryCard({
  category,
  productCount,
  canManage,
  onEdit,
}: {
  category: Category;
  productCount: number;
  canManage: boolean;
  onEdit: () => void;
}) {
  const queryClient = useQueryClient();

  const remove = useMutation({
    mutationFn: () => categoriesApi.remove(category.id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
      await queryClient.invalidateQueries({ queryKey: ["products"] });
      toast.success(result.message ?? "Category removed.");
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not remove the category.",
      ),
  });

  return (
    <Card className="flex flex-row items-center gap-3 p-4">
      <span
        aria-hidden
        className="size-10 shrink-0 rounded-lg border"
        style={{ backgroundColor: category.color ?? "var(--muted)" }}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{category.name}</p>
        <p className="text-muted-foreground text-sm">
          {productCount} {productCount === 1 ? "product" : "products"}
        </p>
      </div>
      {category.parent_id && <Badge variant="outline">Sub</Badge>}
      {canManage && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Actions for ${category.name}`}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onEdit}>Rename</DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              <Trash2 className="size-4" /> Remove
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </Card>
  );
}

function CategoryDialog({
  open,
  category,
  onOpenChange,
}: {
  open: boolean;
  category: Category | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {/* Keyed so switching straight from one category to another resets
            the form rather than showing the previous one's name. */}
        <CategoryForm
          key={category?.id ?? "new"}
          category={category}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function CategoryForm({
  category,
  onDone,
}: {
  category: Category | null;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(category?.name ?? "");
  const [color, setColor] = useState(category?.color ?? SWATCHES[0]);

  const save = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), color };
      return category
        ? categoriesApi.update(category.id, body)
        : categoriesApi.create(body);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
      toast.success(category ? "Category updated." : "Category added.");
      onDone();
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not save the category.",
      ),
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>{category ? "Edit category" : "Add category"}</DialogTitle>
        <DialogDescription>
          Categories group products on the terminal grid.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-1">
        <Field>
          <FieldLabel htmlFor="cat-name">Name</FieldLabel>
          <Input
            id="cat-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </Field>

        <Field>
          <FieldLabel>Tile colour</FieldLabel>
          <div className="flex flex-wrap gap-2">
            {SWATCHES.map((swatch) => (
              <button
                key={swatch}
                type="button"
                aria-label={`Colour ${swatch}`}
                aria-pressed={color === swatch}
                onClick={() => setColor(swatch)}
                style={{ backgroundColor: swatch }}
                className={`size-8 rounded-lg border-2 transition ${
                  color === swatch
                    ? "ring-ring border-background ring-2"
                    : "border-transparent"
                }`}
              />
            ))}
          </div>
          <FieldDescription>
            Cashiers find tiles by colour faster than by reading them.
          </FieldDescription>
        </Field>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={!name.trim() || save.isPending}
        >
          {save.isPending && <Loader2 className="size-4 animate-spin" />}
          {category ? "Save" : "Add category"}
        </Button>
      </DialogFooter>
    </>
  );
}
