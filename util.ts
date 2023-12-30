import papaparse from "papaparse";
import fs from "fs";

/*
< {
<   orderid: 'D01-7098770-3645007',
<   items: 'Elf; ',
<   categories: '',
<   to: '0',
<   date: '2021-12-17',
<   total: '0',
<   shipping: '0',
<   shipping_refund: '0',
<   gift: '0',
<   tax: '3.99',
<   refund: '0',
<   payments: '2021-12-17: $0.00; '
< }
*/

export interface AmazonTransaction {
  orderid: string;
  items: string;
  categories: string;
  to: string;
  date: string;
  total: string;
  shipping: string;
  shipping_refund: string;
  gift: string;
  tax: string;
  refund: string;
  payments: string;
}

export const readJSONFile = (path: string): any | null => {
  if (fs.existsSync(path)) {
    return JSON.parse(fs.readFileSync(path, "utf8"));
  }

  return null;
};

// TODO should type the resulting object here for better checking downstream
export const readCSV = async (
  filePath: string,
): Promise<AmazonTransaction[]> => {
  const csvFile = fs.readFileSync(filePath);
  const csvData = csvFile.toString();

  return new Promise((resolve) => {
    papaparse.parse(csvData, {
      header: true,
      skipEmptyLines: true,
      // 'Original Description' => 'OriginalDescription'
      transformHeader: (header: string) => header.replace(/\s/g, ""),
      complete: (results) => {
        resolve(results.data);
      },
    } as papaparse.ParseConfig<AmazonTransaction>);
  });
};

export const writeCSV = (csvRows: any, filePath: string) => {
  const csvContent = papaparse.unparse(csvRows);
  fs.writeFileSync(filePath, csvContent);
};

export function prettyJSON(json: Object, returnString = false): string {
  return JSON.stringify(json, null, 2);
}
