"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReportJob, ReportType } from "@/lib/api/admin-types";
import { downloadFile } from "@/lib/api/client";
import { reportsApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const REPORT_TYPES: { value: ReportType; label: string; description: string }[] = [
  {
    value: "sales_summary",
    label: "Sales summary",
    description: "Daily takings, tax and margin",
  },
  {
    value: "sales_detailed",
    label: "Sales detail",
    description: "Every line of every sale",
  },
  { value: "tax", label: "Tax", description: "Grouped by rate, ready to file" },
  {
    value: "inventory",
    label: "Inventory valuation",
    description: "On hand and what it cost",
  },
  {
    value: "employee_performance",
    label: "Employee performance",
    description: "Sales by cashier",
  },
];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthStartIso(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const [reportType, setReportType] = useState<ReportType>("sales_summary");
  const [format, setFormat] = useState<"csv" | "pdf">("csv");
  const [dateFrom, setDateFrom] = useState(monthStartIso);
  const [dateTo, setDateTo] = useState(todayIso);

  const jobs = useQuery({
    queryKey: ["reports"],
    queryFn: reportsApi.list,
    // Poll only while something is actually in flight; a dashboard that
    // refetches forever is a battery drain on a shop tablet.
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some(
        (job) => job.status === "pending" || job.status === "running",
      )
        ? 2000
        : false;
    },
    // React Query suspends polling while the window is unfocused. That is the
    // right default for most screens and the wrong one here: the whole point of
    // a background job is that you go and do something else, and returning to a
    // list still showing "pending" for a report that finished minutes ago is
    // worse than the handful of extra requests.
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  });

  const request = useMutation({
    mutationFn: () =>
      reportsApi.request({
        report_type: reportType,
        export_format: format,
        date_from: dateFrom,
        date_to: dateTo,
      }),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      if (job.status === "failed") {
        toast.error(job.error_message ?? "Could not queue the report.");
      } else {
        toast.success("Report queued. It will appear below when ready.");
      }
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not request the report.",
      ),
  });

  const download = useMutation({
    mutationFn: (job: ReportJob) =>
      downloadFile(
        reportsApi.downloadUrl(job.id),
        `${job.report_type}.${job.export_format}`,
      ),
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Download failed."),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Exportable sales, tax and inventory reports."
      />

      <Card>
        <CardHeader>
          <CardTitle>New export</CardTitle>
          <CardDescription>
            Generated in the background, so a long date range never times out your
            browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field className="lg:col-span-2">
              <FieldLabel>Report</FieldLabel>
              <Select
                value={reportType}
                onValueChange={(value) => setReportType(value as ReportType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REPORT_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field>
              <FieldLabel htmlFor="from">From</FieldLabel>
              <Input
                id="from"
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="to">To</FieldLabel>
              <Input
                id="to"
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </Field>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex gap-2">
              {(["csv", "pdf"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setFormat(option)}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
                    format === option
                      ? "border-primary bg-primary/10 font-medium"
                      : "hover:bg-accent",
                  )}
                >
                  {option === "csv" ? (
                    <FileSpreadsheet className="size-4" />
                  ) : (
                    <FileText className="size-4" />
                  )}
                  {option.toUpperCase()}
                </button>
              ))}
            </div>

            <Button
              onClick={() => request.mutate()}
              disabled={request.isPending || dateTo < dateFrom}
            >
              {request.isPending && <Loader2 className="size-4 animate-spin" />}
              Generate report
            </Button>
          </div>

          {dateTo < dateFrom && (
            <p className="text-destructive text-sm">
              The end date is before the start date.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent exports</CardTitle>
          <CardDescription>
            Files are kept for 48 hours, then deleted.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {jobs.isPending ? (
            <div className="space-y-3 p-6">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : (jobs.data?.items ?? []).length === 0 ? (
            <p className="text-muted-foreground py-12 text-center text-sm">
              No exports yet.
            </p>
          ) : (
            <ul className="divide-y">
              {(jobs.data?.items ?? []).map((job) => (
                <li key={job.id} className="flex items-center gap-3 px-6 py-3">
                  <StatusIcon status={job.status} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {REPORT_TYPES.find((t) => t.value === job.report_type)
                        ?.label ?? job.report_type}
                      <span className="text-muted-foreground ml-2 text-xs font-normal uppercase">
                        {job.export_format}
                      </span>
                    </p>
                    <p className="text-muted-foreground truncate text-xs">
                      {job.params.label ?? ""} · requested{" "}
                      {formatDateTime(job.created_at)}
                      {job.error_message && (
                        <span className="text-destructive">
                          {" "}
                          · {job.error_message}
                        </span>
                      )}
                    </p>
                  </div>

                  <Badge
                    variant={job.status === "failed" ? "destructive" : "outline"}
                  >
                    {job.status}
                  </Badge>

                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!job.is_downloadable || download.isPending}
                    onClick={() => download.mutate(job)}
                  >
                    <Download className="size-4" />
                    <span className="hidden sm:inline">Download</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Status carries an icon and a word, never colour alone. */
function StatusIcon({ status }: { status: ReportJob["status"] }) {
  if (status === "completed") {
    return <CheckCircle2 className="text-primary size-5 shrink-0" />;
  }
  if (status === "failed") {
    return <AlertCircle className="text-destructive size-5 shrink-0" />;
  }
  if (status === "running") {
    return (
      <Loader2 className="text-muted-foreground size-5 shrink-0 animate-spin" />
    );
  }
  return <Clock className="text-muted-foreground size-5 shrink-0" />;
}
