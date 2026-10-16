import argparse
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def load_df(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Feature matrix not found at {path}")
    df = pd.read_csv(path)
    return df


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def plot_primary_pathway_pie(df, outdir):
    col = 'primary_pathway'
    if col not in df.columns:
        print(f"Skipping pie: column '{col}' not found")
        return
    counts = df[col].fillna('Unknown').value_counts()
    plt.figure(figsize=(8,8))
    counts.plot.pie(autopct='%1.1f%%', startangle=90)
    plt.title('Primary Pathway Distribution')
    plt.ylabel('')
    fn = os.path.join(outdir, 'primary_pathway_pie.png')
    plt.tight_layout()
    plt.savefig(fn)
    plt.close()
    print('Saved', fn)


def plot_gap_score_hist(df, outdir):
    col = 'gap_score'
    if col not in df.columns:
        print(f"Skipping histogram: column '{col}' not found")
        return
    plt.figure(figsize=(8,5))
    sns.histplot(df[col].dropna(), bins=30, kde=True)
    plt.title('Gap Score Distribution')
    plt.xlabel('gap_score')
    fn = os.path.join(outdir, 'gap_score_hist.png')
    plt.tight_layout()
    plt.savefig(fn)
    plt.close()
    print('Saved', fn)


def plot_tfidf_vs_skill_overlap(df, outdir):
    x = 'skill_overlap'
    y = 'tfidf_score'
    if x not in df.columns or y not in df.columns:
        print(f"Skipping scatter: columns '{x}' or '{y}' not found")
        return
    plt.figure(figsize=(8,6))
    sns.scatterplot(data=df, x=x, y=y, hue=df.get('primary_pathway'), alpha=0.7, legend=False)
    plt.title('TF-IDF vs Skill Overlap')
    plt.xlabel(x)
    plt.ylabel(y)
    fn = os.path.join(outdir, 'tfidf_vs_skill_overlap.png')
    plt.tight_layout()
    plt.savefig(fn)
    plt.close()
    print('Saved', fn)


def plot_top_courses_by_tfidf(df, outdir, top_n=10):
    col = 'course_code'
    score = 'tfidf_score'
    if col not in df.columns or score not in df.columns:
        print(f"Skipping top courses: columns '{col}' or '{score}' not found")
        return
    df2 = df[[col, score]].dropna()
    df2 = df2.groupby(col)[score].mean().nlargest(top_n).sort_values()
    plt.figure(figsize=(10,6))
    df2.plot.barh(color='C0')
    plt.xlabel('Average TF-IDF Score')
    plt.title(f'Top {top_n} Courses by Average TF-IDF')
    fn = os.path.join(outdir, 'top_courses_tfidf.png')
    plt.tight_layout()
    plt.savefig(fn)
    plt.close()
    print('Saved', fn)


def main():
    p = argparse.ArgumentParser(description='Visualize feature matrix')
    p.add_argument('--input', '-i', default='data/handoff/feature_matrix.csv')
    p.add_argument('--outdir', '-o', default='outputs/figures')
    args = p.parse_args()

    try:
        df = load_df(args.input)
    except Exception as e:
        print('Error loading feature matrix:', e)
        sys.exit(1)

    ensure_dir(args.outdir)

    plot_primary_pathway_pie(df, args.outdir)
    plot_gap_score_hist(df, args.outdir)
    plot_tfidf_vs_skill_overlap(df, args.outdir)
    plot_top_courses_by_tfidf(df, args.outdir)


if __name__ == '__main__':
    main()
